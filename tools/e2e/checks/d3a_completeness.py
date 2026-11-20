"""D3A E2E-5 (independent path): completeness — per advanced pipeline, record
count equals budget; intensity variants carry their full round artifacts;
dataset manifests exist with counts agreeing with the store; all 54 originals
scored; blocked files present.
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


def main(run_dir, store_dir, orig_dir, run_id):
    report = {"check": "d3a-completeness", "pass": False, "details": []}
    pipes = cfg.load("pipelines.yaml")
    for pipe in pipes["d3a_pipelines"]:
        budget = cfg.require_resolved(pipes, "pipeline_%s_budget" % pipe, "config/pipelines.yaml")
        recs = sorted(glob.glob(os.path.join(store_dir, "records", "V-%s-*.json" % pipe)))
        if len(recs) != budget:
            report["details"].append("%s: %d records != budget %d" % (pipe, len(recs), budget))
        blocked_path = os.path.join(store_dir, "blocked-%s-%s.json" % (run_id, pipe))
        if not os.path.exists(blocked_path):
            report["details"].append("%s: blocked file missing" % pipe)
        man_path = os.path.join(ROOT, "datasets", "d3a", "manifest-%s.json" % pipe)
        if not os.path.exists(man_path):
            report["details"].append("%s: dataset manifest missing" % pipe)
        else:
            manifest = json.load(open(man_path))
            if manifest.get("variant_count") != len(recs):
                report["details"].append("%s: manifest count != store" % pipe)
        if pipe.startswith("d3a-i"):
            rounds_expected = int(pipe.split("-i")[1])
            # Loader returns list elements as strings; normalize before compare.
            intensities = [int(x) for x in pipes["d3a_intensities"]]
            if rounds_expected not in intensities:
                report["details"].append("%s: rounds %d not in %s"
                                         % (pipe, rounds_expected, intensities))
            for rec_path in recs:
                vid = json.load(open(rec_path))["sample_id"]
                rounds_path = os.path.join(store_dir, "intermediates", vid, "rounds.json")
                if not os.path.exists(rounds_path):
                    report["details"].append("%s: rounds.json missing" % vid)
                    continue
                rounds = json.load(open(rounds_path))["rounds"]
                if len(rounds) != rounds_expected:
                    report["details"].append("%s: %d rounds != %d"
                                             % (vid, len(rounds), rounds_expected))
                for entry in rounds:
                    if not os.path.isfile(os.path.join(store_dir, entry["file"])):
                        report["details"].append("%s: round file missing" % vid)
    orig_recs = glob.glob(os.path.join(orig_dir, "records", "*.json"))
    if len(orig_recs) != 54:
        report["details"].append("originals: %d != 54" % len(orig_recs))
    if not report["details"]:
        report["details"].append("6 pipelines at budget with rounds + manifests; 54 originals")
    report["pass"] = not [d for d in report["details"] if "at budget" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3a-completeness.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3a-completeness: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
