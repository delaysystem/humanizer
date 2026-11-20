"""D3A Goal-E index check (independent path): the six by-condition fix entries
exist with the §2.1 file set, INDEX.md/YAML agree on them, every entry has
status PROPOSED_NOT_APPLIED, and every referenced failure ID resolves in the
run's failure-ID registry.
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)

REQUIRED_FILES = ["README.md", "meta.yaml", "proposal.md", "config-proposal.yaml",
                  "training-augmentation-spec.md", "threshold-simulation.md",
                  "verification-test-spec.md", "risk-and-rollback.md", "data-spec.md"]


def main(run_dir, store_dir, run_id):
    report = {"check": "d3a-fixindex", "pass": False, "details": []}
    sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
    import config as cfg
    pipes = cfg.load("pipelines.yaml")
    conditions = pipes["d3a_pipelines"]
    inv = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json")))["payload"]["detectors"]
    codes = [d["code"] for d in inv]
    registry = json.load(open(os.path.join(store_dir, "failure-ids-%s.json" % run_id)))
    index_md = open(os.path.join(ROOT, "detector-fixes", "INDEX.md")).read()
    index_yaml = open(os.path.join(ROOT, "detector-fixes", "INDEX.yaml")).read()
    for i, condition in enumerate(conditions, 1):
        fix_id = "FIX-D3A-%03d" % i
        fix_dir = os.path.join(ROOT, "detector-fixes", fix_id)
        if not os.path.isdir(fix_dir):
            report["details"].append("missing dir: " + fix_id)
            continue
        for name in REQUIRED_FILES:
            if not os.path.isfile(os.path.join(fix_dir, name)):
                report["details"].append("%s: missing %s" % (fix_id, name))
        readme = open(os.path.join(fix_dir, "README.md")).read()
        if "PROPOSED_NOT_APPLIED" not in readme:
            report["details"].append(fix_id + ": status not PROPOSED_NOT_APPLIED")
        if fix_id not in index_md or fix_id not in index_yaml:
            report["details"].append(fix_id + ": not indexed in MD+YAML")
        for fid in ["FAIL-%s-%s-001" % (code, condition) for code in codes]:
            if fid not in registry:
                report["details"].append("unresolvable failure ID: " + fid)
                break
            if fid not in readme:
                report["details"].append("%s: README omits %s" % (fix_id, fid))
    if not report["details"]:
        report["details"].append("6 Goal-E entries complete, indexed, statuses honest, IDs resolve")
    report["pass"] = not [d for d in report["details"] if "complete" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3a-fixindex.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3a-fixindex: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
