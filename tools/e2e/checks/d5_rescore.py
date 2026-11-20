"""D5 E2E-3 (independent path): compare rescoring reports to frozen records —
overall score/verdict/flagged/total plus all 23 per-engine score/verdict/
details must match within the D2 spread tolerance (score_rerun_tolerance).
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def main(run_dir, d3_store, d3a_store, rescores_dir):
    report = {"check": "d5-rescore", "pass": False, "details": []}
    tols = cfg.load("tolerances.yaml")
    tol = cfg.require_resolved(tols, "score_rerun_tolerance", "config/tolerances.yaml")
    blocked = json.load(open(os.path.join(run_dir, "rescore-blocked.json")))
    if blocked:
        report["details"].append("%d rescorings blocked (endpoint failure)" % len(blocked))
    compared, worst = 0, 0.0
    diffs = []
    for store_dir in (d3_store, d3a_store):
        for path in sorted(glob.glob(os.path.join(store_dir, "records", "V-*.json"))):
            rec = json.load(open(path))
            vid = rec["sample_id"]
            raw_path = os.path.join(rescores_dir, vid + ".json")
            if not os.path.isfile(raw_path):
                diffs.append("%s: no rescore report" % vid)
                continue
            raw = json.load(open(raw_path))
            frozen_overall = rec.get("overall_verbatim", {})
            for field in ("overall_score", "overall_verdict", "engines_flagged", "engines_total"):
                if raw.get(field) != frozen_overall.get(field):
                    diffs.append("%s: %s %r != %r"
                                 % (vid, field, raw.get(field), frozen_overall.get(field)))
            want = {e["engine_name"]: (e["score"], e["verdict"], e["details"])
                    for e in raw["engine_results"]}
            for name, frozen in sorted(rec["per_detector_scores"].items()):
                got = want.get(name)
                if got is None:
                    diffs.append("%s: engine %s missing in rescore" % (vid, name))
                    continue
                delta = abs(got[0] - frozen["score"])
                worst = max(worst, delta)
                if delta > tol or got[1] != frozen["verdict"] or got[2] != frozen["details"]:
                    diffs.append("%s: engine %s drifts (d=%.4f)" % (vid, name, delta))
            compared += 1
    report["details"].extend(diffs[:10])
    if not diffs and not blocked:
        report["details"].append("%d variants rescored: all scores within %s (worst d=%.4f)"
                                 % (compared, tol, worst))
    report["pass"] = not diffs and not blocked
    json.dump(report, open(os.path.join(run_dir, "check-d5-rescore.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d5-rescore: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
