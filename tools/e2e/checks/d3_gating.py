"""D3 E2E-3 (independent path): fidelity gating — every record carries a
fidelity result; fidelity_passing equals (cosine >= config threshold); the
per-run exclusion list names exactly the failing variant IDs. (The gate model
itself is covered by d2_fidelity; this check replays the rule, not the model.)
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
    report = {"check": "d3-gating", "pass": False, "details": []}
    threshold = cfg.require_resolved(cfg.load("fidelity.yaml"), "fidelity_threshold",
                                     "config/fidelity.yaml")
    failing, passing = [], []
    for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
        record = json.load(open(path))
        fidel = record.get("fidelity") or {}
        if "cosine" not in fidel or "fidelity_passing" not in fidel:
            report["details"].append("%s: fidelity result missing" % record.get("sample_id"))
            continue
        expect = fidel["cosine"] >= threshold
        if bool(fidel["fidelity_passing"]) != expect:
            report["details"].append("%s: passing=%s vs rule %s (cosine %s)"
                                     % (record["sample_id"], fidel["fidelity_passing"],
                                        expect, fidel["cosine"]))
        (passing if expect else failing).append(record["sample_id"])
    listed = set()
    for pipe in cfg.load("pipelines.yaml")["dataset_pipelines"]:
        excl = json.load(open(os.path.join(store_dir, "excluded-%s-%s.json" % (run_id, pipe))))
        listed.update(excl.get("degraded_variant_ids", []))
    if set(failing) != listed:
        report["details"].append("exclusion list != failing set (missing %s, extra %s)"
                                 % (sorted(set(failing) - listed), sorted(listed - set(failing))))
    if not report["details"]:
        report["details"].append("%d passing, %d degraded; exclusion list exact"
                                 % (len(passing), len(failing)))
    report["pass"] = not [d for d in report["details"] if "exclusion list exact" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-gating.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-gating: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
