"""D3 E2E-2 (independent path): label + parameter preservation — every record's
original resolves in the D1 manifest with an unchanged ground-truth label, and
carries full transform parameters (pipeline + per-step name/version/params).
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)

# origin: D3 decision — preservation is always judged against frozen dataset v1.
DATASET_MANIFEST = os.path.join(ROOT, "datasets", "v1", "manifest.json")


def main(run_dir, store_dir):
    report = {"check": "d3-preservation", "pass": False, "details": []}
    manifest = json.load(open(DATASET_MANIFEST))
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    count = 0
    for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
        record = json.load(open(path))
        count += 1
        source = by_id.get(record.get("original_id"))
        if source is None:
            report["details"].append("%s: unresolvable original" % record.get("sample_id"))
            continue
        if record.get("ground_truth_label") != source["ground_truth_label"]:
            report["details"].append("%s: label changed" % record["sample_id"])
        transform = record.get("transform_params", {})
        if not transform.get("pipeline") or not transform.get("steps"):
            report["details"].append("%s: transform params missing" % record["sample_id"])
        for step in transform.get("steps", []):
            if not step.get("step") or not step.get("version") or "params" not in step:
                report["details"].append("%s: step entry incomplete" % record["sample_id"])
        variant = os.path.join(store_dir, record.get("variant_text_ref", ""))
        if not os.path.isfile(variant):
            report["details"].append("%s: variant file missing" % record["sample_id"])
    if not report["details"]:
        report["details"].append("%d records: labels + params + variant files intact" % count)
    report["pass"] = not [d for d in report["details"] if "intact" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-preservation.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-preservation: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
