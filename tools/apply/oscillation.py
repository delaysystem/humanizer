"""Apply-phase analysis (NOT a fix): batch demonstration of what the
consistency proposal would flag on frozen logged scores.

For each AI original and detector, compares verdicts across the four
sweep intensities (i1/i3/i5/i10); a sample whose verdicts disagree would
be routed to human review under the proposal. Combos have no intensity
axis, so the demonstration covers sweep conditions only (recorded, not
estimated). Read-only over frozen stores. Writes
build/evidence/APPLY/oscillation.json.
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def main():
    inv = load_json(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json"))["payload"]["detectors"]
    names = [d["name"] for d in inv]
    by_orig = {}
    for path in sorted(glob.glob(os.path.join(
            ROOT, "results/d3a/records/V-d3a-i[0-9]*.json"))):
        rec = load_json(path)
        by_orig.setdefault(rec["original_id"], {})[rec["condition_id"]] = rec
    per_detector, flagged = {}, []
    for name in names:
        osc = 0
        for oid in sorted(by_orig):
            conds = by_orig[oid]
            if sorted(conds) != ["d3a-i1", "d3a-i10", "d3a-i3", "d3a-i5"]:
                raise ValueError("incomplete intensity set for " + oid)
            verdicts = [conds[c]["per_detector_scores"][name]["verdict"]
                        for c in ("d3a-i1", "d3a-i3", "d3a-i5", "d3a-i10")]
            if len(set(verdicts)) > 1:
                osc += 1
                flagged.append({"original_id": oid, "detector": name,
                                "verdicts": verdicts})
        per_detector[name] = {"oscillating_originals": osc, "of_n": len(by_orig)}
    out = {"coverage": "sweep intensities only; combos have no intensity axis",
           "originals_n": len(by_orig),
           "per_detector": per_detector,
           "would_flag_n": len(flagged),
           "would_flag": flagged}
    with open(os.path.join(ROOT, "build/evidence/APPLY/oscillation.json"), "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    print("originals: %d, oscillating (detector, original) pairs: %d"
          % (len(by_orig), len(flagged)))
    for name in names:
        if per_detector[name]["oscillating_originals"]:
            print("  %s: %d" % (name, per_detector[name]["oscillating_originals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
