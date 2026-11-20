"""D3 E2E-2b (independent path): variant-ID uniqueness — zero duplicates and
zero collisions across conditions (IDs embed the pipeline by construction).
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)


def main(run_dir, store_dir):
    report = {"check": "d3-uniqueness", "pass": False, "details": []}
    ids = []
    for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
        ids.append(json.load(open(path))["sample_id"])
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(store_dir, "records", "*.json")))
    expected_files = sorted(i + ".json" for i in ids)
    if dupes:
        report["details"].append("duplicate IDs: %s" % dupes)
    if files != expected_files:
        report["details"].append("record filenames diverge from IDs")
    if not report["details"]:
        report["details"].append("%d unique variant IDs, zero collisions" % len(ids))
    report["pass"] = not [d for d in report["details"] if "zero collisions" not in d]
    json.dump(ids, open(os.path.join(run_dir, "variant-id-list.json"), "w"), indent=2)
    json.dump(report, open(os.path.join(run_dir, "check-d3-uniqueness.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-uniqueness: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
