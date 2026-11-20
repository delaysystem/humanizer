"""D3A E2E-6 (independent path): preservation + provenance length — labels,
params, and variant files intact (as D3), and every variant's provenance chain
length equals its pipeline's declared step count.
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


def main(run_dir, store_dir):
    report = {"check": "d3a-preservation", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(ROOT, "datasets", "v1", "manifest.json")))
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    pipes = cfg.load("pipelines.yaml")
    count = 0
    for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
        record = json.load(open(path))
        count += 1
        source = by_id.get(record.get("original_id"))
        if source is None or record.get("ground_truth_label") != source["ground_truth_label"]:
            report["details"].append("%s: original/label broken" % record.get("sample_id"))
        if not record.get("transform_params", {}).get("steps"):
            report["details"].append("%s: params missing" % record.get("sample_id"))
        if not os.path.isfile(os.path.join(store_dir, record.get("variant_text_ref", ""))):
            report["details"].append("%s: variant file missing" % record.get("sample_id"))
        declared = len(pipes["pipeline_%s_steps" % record["condition_id"]])
        if len(record.get("provenance", [])) != declared:
            report["details"].append("%s: chain %d != declared %d"
                                     % (record["sample_id"], len(record.get("provenance", [])),
                                        declared))
    if not report["details"]:
        report["details"].append("%d records intact with exact provenance lengths" % count)
    report["pass"] = not [d for d in report["details"] if "exact provenance lengths" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3a-preservation.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3a-preservation: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
