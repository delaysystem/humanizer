"""§3B provenance (independent path): replay the audit records — every dataset
record's provenance chain equals its pipeline's declared step sequence
(names + versions in order), its original resolves in D1 with an unchanged
label, and only dataset pipelines appear in the store.
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
    report = {"check": "d3-provenance", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(ROOT, "datasets", "v1", "manifest.json")))
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    pipes = cfg.load("pipelines.yaml")
    dataset_pipes = set(pipes["dataset_pipelines"])
    for pipe in pipes["dataset_pipelines"]:
        audit_path = os.path.join(store_dir, "audit-%s-%s.json" % (run_id, pipe))
        if not os.path.exists(audit_path):
            report["details"].append("missing audit record: " + pipe)
    count = 0
    for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
        record = json.load(open(path))
        count += 1
        pipe = record.get("condition_id")
        if pipe not in dataset_pipes:
            report["details"].append("non-dataset pipeline in store: %s" % pipe)
            continue
        declared = pipes["pipeline_%s_steps" % pipe]
        chain = ["%s@%s" % (c["step"], c["version"]) for c in record.get("provenance", [])]
        if chain != declared:
            report["details"].append("%s: chain %s != declared %s"
                                     % (record["sample_id"], chain, declared))
        source = by_id.get(record.get("original_id"))
        if source is None or record.get("ground_truth_label") != source["ground_truth_label"]:
            report["details"].append("%s: original/label broken" % record["sample_id"])
    if not report["details"]:
        report["details"].append("%d records replay cleanly against audit + pipeline defs" % count)
    report["pass"] = not [d for d in report["details"] if "replay cleanly" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-provenance.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-provenance: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
