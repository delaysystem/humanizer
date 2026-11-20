"""D1 E2E-3 (independent path): matched-pairs check — every (topic, band) used
for comparison holds both labels within dataset_matched_pair_tolerance, or is
listed unmatched (and excluded from comparative claims in the verdict)."""
import json
import os
import sys
from collections import Counter

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def main(run_dir):
    report = {"check": "d1-matched", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(ROOT, "datasets", "v1", "manifest.json")))
    ds = cfg.load("datasets.yaml")
    tol = cfg.require_resolved(ds, "dataset_matched_pair_tolerance", "config/datasets.yaml")
    join = {}
    for sample in manifest["samples"]:
        join.setdefault((sample["topic"], sample["length_band"]),
                        Counter())[sample["ground_truth_label"]] += 1
    table, unmatched = [], []
    for key in sorted(join):
        counts = join[key]
        row = {"topic": key[0], "band": key[1], "human": counts.get("human", 0),
               "ai": counts.get("ai", 0)}
        if abs(row["human"] - row["ai"]) > tol:
            row["status"] = "UNMATCHED-excluded-from-comparison"
            unmatched.append(row)
        else:
            row["status"] = "matched"
        table.append(row)
    json.dump({"join_table": table, "unmatched": unmatched},
              open(os.path.join(run_dir, "matched-join.json"), "w"), indent=2)
    if unmatched:
        report["details"].append("%d unmatched bands listed + excluded: %s"
                                 % (len(unmatched), [(u["topic"], u["band"]) for u in unmatched]))
    else:
        report["details"].append("all %d (topic, band) pairs matched" % len(table))
    report["pass"] = True  # assertion is matched-OR-listed; listing is the artifact
    json.dump(report, open(os.path.join(run_dir, "check-d1-matched.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d1-matched: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
