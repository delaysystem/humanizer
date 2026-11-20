"""D3 E2E-1 (independent path): condition completeness — per dataset pipeline,
store-record count equals the config budget. Bodhan health was established by
D3 Probe 1 (both legs HTTP 200), so no condition carries an EXTERNAL-BLOCKED
row; any transport shortfall fails honestly here (retries absorb flakes).
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


def main(run_dir, store_dir, run_id):
    report = {"check": "d3-completeness", "pass": False, "details": []}
    pipes = cfg.load("pipelines.yaml")
    records = {}
    for path in glob.glob(os.path.join(store_dir, "records", "*.json")):
        record = json.load(open(path))
        records.setdefault(record["condition_id"], []).append(record["sample_id"])
    for pipe in pipes["dataset_pipelines"]:
        budget = cfg.require_resolved(pipes, "pipeline_%s_budget" % pipe, "config/pipelines.yaml")
        got = len(records.get(pipe, []))
        blocked_path = os.path.join(store_dir, "blocked-%s-%s.json" % (run_id, pipe))
        blocked = json.load(open(blocked_path)) if os.path.exists(blocked_path) else None
        if blocked is None:
            report["details"].append("%s: blocked file missing" % pipe)
        elif got != budget:
            report["details"].append("%s: %d records != budget %d (blocked: %d)"
                                     % (pipe, got, budget, len(blocked)))
        else:
            report["details"].append("%s: %d/%d records, %d blocked"
                                     % (pipe, got, budget, len(blocked)))
    unexpected = set(records) - set(pipes["dataset_pipelines"])
    if unexpected:
        report["details"].append("non-dataset records in store: %s" % sorted(unexpected))
    report["pass"] = not [d for d in report["details"] if "records, " not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-completeness.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-completeness: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
