"""Apply-phase sweep: run the frozen D4 threshold-sweep method offline on
logged scores for the six D3A entry-conditions.

Imports sweep/best_fact/snapshot_sha plus the grid from the frozen
d4_analyze (the method the entries' threshold-simulation.md names); no
live deployment is touched. Per detector per condition it records the
full curve, the snapshot hash, the best_fact line, the frozen current
verdict flips, and a candidate operating point under the frozen rule:
best-fact T only when it is within the human-FPR bound, differs from
the deployed 0.65 slop boundary, and lowers simulated flips vs the
0.65 reference. No candidate is a result, not a failure.
Writes build/evidence/APPLY/sweep-<condition>.json (deterministic).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "analysis"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402
from d4_analyze import sweep, best_fact, snapshot_sha  # noqa: E402 — frozen method

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)

DEPLOYED_SLOP = 0.65


def load_json(rel):
    with open(os.path.join(ROOT, rel)) as fh:
        return json.load(fh)


def main():
    analysis = cfg.load("analysis.yaml")
    fpr_bound = cfg.require_resolved(analysis, "analysis_human_fpr_bound",
                                     "config/analysis.yaml")
    d4cfg = cfg.load("d4.yaml")
    frozen_run = cfg.require_resolved(d4cfg, "d4_d3a_tables_run_id", "config/d4.yaml")
    frozen_tables = load_json("results/d3a/flip-tables-%s.json" % frozen_run)
    inv = load_json("build/evidence/D0/frozen/inventory.json")["payload"]["detectors"]
    names = [d["name"] for d in inv]
    originals = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "results/d3a-originals/records/*.json"))):
        rec = load_json(os.path.relpath(path, ROOT))
        originals[rec["sample_id"]] = rec["per_detector_scores"]
    humans = [load_json(os.path.relpath(p, ROOT)) for p in sorted(
        glob.glob(os.path.join(ROOT, "results/d3a-originals/records/*.json")))]
    humans = [r for r in humans if r["ground_truth_label"] == "human"]
    human_scores = {name: [r["per_detector_scores"][name]["score"] for r in humans]
                    for name in names}
    variants = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "results/d3a/records/*.json"))):
        rec = load_json(os.path.relpath(path, ROOT))
        variants.setdefault(rec["condition_id"], []).append(rec)
    out_dir = os.path.join(ROOT, "build", "evidence", "APPLY")
    os.makedirs(out_dir, exist_ok=True)
    total_candidates = 0
    for condition in sorted(frozen_tables):
        passing = [v for v in variants[condition]
                   if (v.get("fidelity") or {}).get("fidelity_passing")]
        detectors = {}
        for name in names:
            rows = sweep(name, passing, originals, human_scores[name], fpr_bound)
            fact = best_fact(rows, fpr_bound)
            ref = [r for r in rows if r["T"] == DEPLOYED_SLOP][0]
            inside = [r for r in rows if r["within_bound"]]
            candidate = None
            if inside:
                best = min(inside, key=lambda r: (r["flips"], r["human_fpr"], r["T"]))
                if best["T"] != DEPLOYED_SLOP and best["flips"] < ref["flips"]:
                    candidate = best["T"]
                    total_candidates += 1
            detectors[name] = {
                "current_verdict_flips": frozen_tables[condition]["detectors"][name]["flips"],
                "snapshot_sha": snapshot_sha(name, passing, originals),
                "best_fact": fact, "candidate_T": candidate, "curve": rows}
        with open(os.path.join(out_dir, "sweep-%s.json" % condition), "w") as fh:
            json.dump({"condition": condition, "fpr_bound": fpr_bound,
                       "deployed_slop_boundary": DEPLOYED_SLOP,
                       "frozen_tables_run": frozen_run,
                       "detectors": detectors}, fh, indent=2, sort_keys=True)
        n_cand = sum(1 for d in detectors.values() if d["candidate_T"] is not None)
        print("%s: %d/23 candidate operating points" % (condition, n_cand))
    print("total candidates: %d" % total_candidates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
