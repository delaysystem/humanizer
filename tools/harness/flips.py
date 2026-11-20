"""Goal-D flip tables (D3A build) — per detector, per advanced condition.

Reads the D3A store + scored originals, applies the frozen flip definition
(original AI + variant human + fidelity-passing; suspicious never flips),
writes flip-tables.json + the stable failure-ID registry (all 23 x 6 groups,
counts may be 0). The d3a_flips check recomputes all of this independently.
Usage: flips.py --store <results/d3a> --originals <results/d3a-originals> --out <tables.json> --ids-out <failure-ids.json>
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg


def load_mapping():
    analysis = cfg.load("analysis.yaml")
    return (set(analysis["flip_verdict_map_ai"]), set(analysis["flip_verdict_map_human"]))


def build(store_dir, originals_dir):
    ai_map, human_map = load_mapping()
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    inv = json.load(open(os.path.join(
        root, "build/evidence/D0/frozen/inventory.json")))["payload"]["detectors"]
    canonical = [(d["name"], d["code"]) for d in inv]
    by_condition = {}
    for path in glob.glob(os.path.join(store_dir, "records", "*.json")):
        record = json.load(open(path))
        by_condition.setdefault(record["condition_id"], []).append(record)
    originals = {}
    for path in glob.glob(os.path.join(originals_dir, "records", "*.json")):
        record = json.load(open(path))
        originals[record["sample_id"]] = record["per_detector_scores"]
    tables, registry = {}, {}
    for condition in sorted(by_condition):
        variants = by_condition[condition]
        passing = [v for v in variants if (v.get("fidelity") or {}).get("fidelity_passing")]
        rows = {}
        for detector, code in canonical:
            flips = 0
            for variant in passing:
                orig_scores = originals.get(variant["original_id"], {})
                orig_verdict = (orig_scores.get(detector) or {}).get("verdict")
                var_entry = variant["per_detector_scores"].get(detector, {})
                if orig_verdict in ai_map and var_entry.get("verdict") in human_map:
                    flips += 1
            fid = "FAIL-%s-%s-001" % (code, condition)
            rows[detector] = {"fidelity_passing_n": len(passing), "flips": flips,
                              "flip_rate": round(flips / len(passing), 4) if passing else None,
                              "failure_id": fid}
            registry[fid] = {"detector": detector, "condition": condition,
                             "fidelity_passing_n": len(passing), "flips": flips}
        tables[condition] = {"variant_n": len(variants), "fidelity_passing_n": len(passing),
                             "detectors": rows}
    return tables, registry


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--originals", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ids-out", required=True)
    args = parser.parse_args(argv)
    tables, registry = build(args.store, args.originals)
    with open(args.out, "w") as fh:
        json.dump(tables, fh, indent=2)
    with open(args.ids_out, "w") as fh:
        json.dump(registry, fh, indent=2)
    print("flip tables: %d conditions, %d failure IDs" % (len(tables), len(registry)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
