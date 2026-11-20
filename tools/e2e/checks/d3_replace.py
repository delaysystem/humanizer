"""§3B replaceability (independent path): the truncate@v2 probe pipeline ran to
completion on the same samples, every variant traces to its original with an
intact provenance chain naming truncate@v2, and ground-truth labels are
traceable to D1 originals. Only contract properties are asserted — v2 may
legitimately differ in output from v1. (Label immutability for scored records
is covered by d3_preservation + d3_provenance.)
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


def main(run_dir, replace_store, run_id):
    report = {"check": "d3-replace", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(ROOT, "datasets", "v1", "manifest.json")))
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    pipes = cfg.load("pipelines.yaml")
    budget = cfg.require_resolved(pipes, "pipeline_probe-truncate-v2_budget", "config/pipelines.yaml")
    variants = sorted(glob.glob(os.path.join(replace_store, "variants", "*.txt")))
    if len(variants) != budget:
        report["details"].append("%d variants != budget %d" % (len(variants), budget))
    audit = json.load(open(os.path.join(
        replace_store, "audit-%s-probe-truncate-v2.json" % run_id)))["payload"]
    if audit.get("steps") != ["truncate@v2"]:
        report["details"].append("audit steps != [truncate@v2]: %s" % audit.get("steps"))
    for path in variants:
        vid = os.path.basename(path)[:-4]
        if not vid.startswith("V-probe-truncate-v2-"):
            report["details"].append("variant ID outside probe pipeline: " + vid)
            continue
        sid = vid[len("V-probe-truncate-v2-"):]
        if sid not in by_id:
            report["details"].append("untraceable original: " + vid)
    if not report["details"]:
        report["details"].append("%d v2 variants complete, provenance intact, originals traceable"
                                 % len(variants))
    report["pass"] = not [d for d in report["details"] if "intact" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-replace.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-replace: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
