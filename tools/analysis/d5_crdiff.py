"""D5: cleanroom diff — mechanically compare a fresh-checkout re-run tree
against this repo: every record's overall + per-engine scores, the
detector-fixes tree, the D4 analysis report, and dataset manifests.
Writes build/evidence/D5/cleanroom-diff.json (inputs to d5_report.py).

Usage: d5_crdiff.py --cleanroom /tmp/d5-cleanroom --out build/evidence/D5/cleanroom-diff.json
"""
import argparse
import filecmp
import glob
import hashlib
import json
import os
import sys


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_scores(repo, room):
    compared, mismatches, worst = 0, [], 0.0
    for store in ("results/d2", "results/d3", "results/d3a", "results/d3a-originals"):
        for path in sorted(glob.glob(os.path.join(repo, store, "records", "*.json"))):
            rel = os.path.relpath(path, repo)
            other = os.path.join(room, rel)
            if not os.path.isfile(other):
                mismatches.append(rel + ": missing in cleanroom")
                continue
            rec_a = json.load(open(path))
            rec_b = json.load(open(other))
            compared += 1
            for field in ("overall_score", "overall_verdict", "engines_flagged", "engines_total"):
                if rec_a["overall_verbatim"][field] != rec_b["overall_verbatim"][field]:
                    mismatches.append("%s: %s differs" % (rel, field))
            for name, eng_a in sorted(rec_a["per_detector_scores"].items()):
                eng_b = rec_b["per_detector_scores"][name]
                delta = abs(eng_a["score"] - eng_b["score"])
                worst = max(worst, delta)
                if delta != 0.0 or eng_a["verdict"] != eng_b["verdict"]:
                    mismatches.append("%s: %s drifts (d=%.4f)" % (rel, name, delta))
    return {"compared": compared, "mismatches": mismatches, "worst_delta": worst}


def compare_tree(repo, room, rel_dir):
    only_here, differ = [], []
    for base, _dirs, files in os.walk(os.path.join(repo, rel_dir)):
        for name in sorted(files):
            if name.endswith((".pyc", ".log")):
                continue
            rel = os.path.relpath(os.path.join(base, name), repo)
            other = os.path.join(room, rel)
            if not os.path.isfile(other):
                only_here.append(rel)
            elif sha_file(os.path.join(repo, rel)) != sha_file(other):
                differ.append(rel)
    return {"only_in_repo": sorted(only_here), "differing": sorted(differ)}


def main(args):
    repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", ".."))
    scores = compare_scores(repo, args.cleanroom)
    fixes = compare_tree(repo, args.cleanroom, "detector-fixes")
    report_a = os.path.join(repo, "build", "evidence", "D4", "d4-analysis-report.json")
    report_b = os.path.join(args.cleanroom, "build", "evidence", "D4", "d4-analysis-report.json")
    report_same = (os.path.isfile(report_b) and sha_file(report_a) == sha_file(report_b))
    manifests = {}
    for path in sorted(glob.glob(os.path.join(repo, "datasets", "d3a", "*.json"))):
        rel = os.path.relpath(path, repo)
        other = os.path.join(args.cleanroom, rel)
        same = False
        runs = []
        if os.path.isfile(other):
            mine = json.load(open(path))
            theirs = json.load(open(other))
            runs = [mine.pop("producing_run_id", None), theirs.pop("producing_run_id", None)]
            same = mine == theirs
        manifests[rel] = {"identical_except_run_id": same, "run_ids": runs}
    out = {"scores": scores, "fixes_tree": fixes, "d4_report_identical": report_same,
           "manifests_identical": manifests}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    bad = bool(scores["mismatches"] or fixes["only_in_repo"] or fixes["differing"]
               or not report_same
               or not all(m["identical_except_run_id"] for m in manifests.values()))
    print("cleanroom diff: %d scores compared, mismatches=%d, fixes_differing=%d, report=%s"
          % (scores["compared"], len(scores["mismatches"]), len(fixes["differing"]),
             "identical" if report_same else "DIFFERS"))
    return 0 if not bad else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="d5_crdiff")
    parser.add_argument("--cleanroom", required=True)
    parser.add_argument("--out", required=True)
    sys.exit(main(parser.parse_args()))
