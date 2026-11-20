"""D3A E2E-9 (independent path): flip-table check — recompute every flip count
from the store + originals using the frozen mapping and require equality with
the published tables; registry IDs stable at 23 per condition.
"""
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg
import flips


def main(run_dir, store_dir, orig_dir, run_id):
    report = {"check": "d3a-flips", "pass": False, "details": []}
    tables_path = os.path.join(store_dir, "flip-tables-%s.json" % run_id)
    ids_path = os.path.join(store_dir, "failure-ids-%s.json" % run_id)
    published_tables = json.load(open(tables_path))
    published_ids = json.load(open(ids_path))
    recomputed_tables, recomputed_ids = flips.build(store_dir, orig_dir)
    if recomputed_tables != published_tables:
        report["details"].append("flip tables differ from recomputation")
    if recomputed_ids != published_ids:
        report["details"].append("failure-ID registry differs from recomputation")
    expected_ids = 23 * len(cfg.load("pipelines.yaml")["d3a_pipelines"])
    if len(published_ids) != expected_ids:
        report["details"].append("%d IDs != %d (23 x conditions)" % (len(published_ids), expected_ids))
    total_flips = sum(d["flips"] for c in published_tables.values() for d in c["detectors"].values())
    if not report["details"]:
        report["details"].append("%d flip rows recomputed exactly; %d total flips; %d stable IDs"
                                 % (sum(len(c["detectors"]) for c in published_tables.values()),
                                    total_flips, len(published_ids)))
    report["pass"] = not [d for d in report["details"] if "recomputed exactly" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3a-flips.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3a-flips: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
