"""Apply-phase verification (independent path): own-code recomputation over
one entry's apply stores with the frozen mapping.

Checks: (1) flips recomputed independently equal the published apply flip
tables exactly; (2) human regression — any new AI verdict on the 27 human
controls fails; (3) score identity vs frozen stores (second implementation
of the check); (4) detection deltas + verdict-distribution shift for the
record. Writes build/evidence/APPLY/verify-<entry>.json with the
mechanical spec outcome (spec_pass). Exit 0 on successful computation;
the JSON carries pass/fail, never silence.
Usage: verify.py --entry FIX-D3A-001
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    args = ap.parse_args(argv)
    entry = args.entry
    apply_cfg = cfg.load("apply.yaml")
    condition = cfg.require_resolved(apply_cfg, "apply_%s_condition" % entry,
                                     "config/apply.yaml")
    analysis = cfg.load("analysis.yaml")
    ai_map = set(analysis["flip_verdict_map_ai"])
    human_map = set(analysis["flip_verdict_map_human"])
    inv = load_json(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json"))["payload"]["detectors"]
    names = [d["name"] for d in inv]
    store_dir = os.path.join(ROOT, "results/apply-" + entry)
    orig_dir = os.path.join(ROOT, "results/apply-" + entry + "-originals")
    run_tag = "apply-" + condition

    new_variants = [load_json(p) for p in sorted(
        glob.glob(os.path.join(store_dir, "records", "*.json")))]
    new_originals = {}
    for p in sorted(glob.glob(os.path.join(orig_dir, "records", "*.json"))):
        rec = load_json(p)
        new_originals[rec["sample_id"]] = rec
    if len(new_variants) != 27 or len(new_originals) != 54:
        raise ValueError("apply store counts %d/%d, want 27/54"
                         % (len(new_variants), len(new_originals)))
    frozen_variants = [load_json(p) for p in sorted(glob.glob(os.path.join(
        ROOT, "results/d3a/records/V-%s-*.json" % condition)))]
    frozen_originals = {}
    for p in sorted(glob.glob(os.path.join(
            ROOT, "results/d3a-originals/records/*.json"))):
        rec = load_json(p)
        frozen_originals[rec["sample_id"]] = rec

    # (3) score identity, recomputed here from both stores.
    score_diffs = []
    for new_rec, frozen_rec in (
            list(zip(sorted(new_variants, key=lambda r: r["sample_id"]),
                     sorted(frozen_variants, key=lambda r: r["sample_id"])))
            + [(new_originals[sid], frozen_originals[sid]) for sid in sorted(new_originals)]):
        if new_rec["sample_id"] != frozen_rec["sample_id"]:
            raise ValueError("sample order mismatch")
        for name in names:
            if (new_rec["per_detector_scores"][name]["score"]
                    != frozen_rec["per_detector_scores"][name]["score"]):
                score_diffs.append("%s/%s" % (new_rec["sample_id"], name))
        for key in ("overall_score", "overall_verdict", "engines_flagged", "engines_total"):
            if new_rec["overall_verbatim"][key] != frozen_rec["overall_verbatim"][key]:
                score_diffs.append("%s/%s" % (new_rec["sample_id"], key))

    # (1) independent flip recomputation on apply data.
    passing = [v for v in new_variants
               if (v.get("fidelity") or {}).get("fidelity_passing")]
    recomputed = {}
    for name in names:
        flips = 0
        for var in passing:
            before = new_originals[var["original_id"]]["per_detector_scores"][name]["verdict"]
            after = var["per_detector_scores"][name]["verdict"]
            if before in ai_map and after in human_map:
                flips += 1
        recomputed[name] = flips
    published = load_json(os.path.join(
        store_dir, "flip-tables-%s.json" % run_tag))[condition]["detectors"]
    published_flips = {name: published[name]["flips"] for name in names}
    flips_match = recomputed == published_flips

    # Frozen entry flips for the before/after comparison.
    d4cfg = cfg.load("d4.yaml")
    frozen_run = cfg.require_resolved(d4cfg, "d4_d3a_tables_run_id", "config/d4.yaml")
    frozen_tables = load_json(os.path.join(
        ROOT, "results/d3a/flip-tables-%s.json" % frozen_run))[condition]["detectors"]
    flips_before = sum(frozen_tables[name]["flips"] for name in names)
    flips_after = sum(recomputed.values())

    # (2) human regression: new AI verdict where frozen was not AI.
    regressions = []
    humans_before_ai, humans_after_ai = 0, 0
    for sid in sorted(new_originals):
        new_rec, frozen_rec = new_originals[sid], frozen_originals[sid]
        if new_rec["ground_truth_label"] != "human":
            continue
        for name in names:
            was_ai = frozen_rec["per_detector_scores"][name]["verdict"] in ai_map
            is_ai = new_rec["per_detector_scores"][name]["verdict"] in ai_map
            humans_before_ai += was_ai
            humans_after_ai += is_ai
            if is_ai and not was_ai:
                regressions.append("%s/%s" % (sid, name))

    # (4) detection deltas + distribution shift.
    ai_ids = [sid for sid in sorted(new_originals)
              if new_originals[sid]["ground_truth_label"] == "ai"]
    det_delta = {}
    for name in names:
        before = sum(1 for sid in ai_ids
                     if frozen_originals[sid]["per_detector_scores"][name]["verdict"]
                     in ai_map)
        after = sum(1 for sid in ai_ids
                    if new_originals[sid]["per_detector_scores"][name]["verdict"] in ai_map)
        det_delta[name] = {"ai_originals_ai_before": before, "ai_originals_ai_after": after}
    dist = {"variants": {}, "originals": {}}
    for label, pairs in (
            ("variants", list(zip(frozen_variants,
                                  sorted(new_variants, key=lambda r: r["sample_id"])))),
            ("originals", [(frozen_originals[sid], new_originals[sid])
                           for sid in sorted(new_originals)])):
        before_c, after_c = {}, {}
        for frozen_rec, new_rec in pairs:
            for name in names:
                before_c[frozen_rec["per_detector_scores"][name]["verdict"]] = \
                    before_c.get(frozen_rec["per_detector_scores"][name]["verdict"], 0) + 1
                after_c[new_rec["per_detector_scores"][name]["verdict"]] = \
                    after_c.get(new_rec["per_detector_scores"][name]["verdict"], 0) + 1
        dist[label] = {"before": before_c, "after": after_c}

    improved = flips_after < flips_before
    human_pass = not regressions
    spec_pass = bool(flips_match and not score_diffs and improved and human_pass)
    verdict = {"entry": entry, "condition": condition,
               "flips_recomputed_match": flips_match,
               "score_identity_diffs": score_diffs,
               "flips_before": flips_before, "flips_after": flips_after,
               "improved": improved,
               "human_regressions": regressions,
               "humans_ai_before": humans_before_ai, "humans_ai_after": humans_after_ai,
               "human_pass": human_pass,
               "detection_delta": det_delta, "distribution": dist,
               "spec_pass": spec_pass}
    with open(os.path.join(ROOT, "build/evidence/APPLY/verify-%s.json" % entry),
              "w") as fh:
        json.dump(verdict, fh, indent=2, sort_keys=True)
    print("%s: flips %d->%d improved=%s human_regressions=%d spec_pass=%s "
          "(recompute_match=%s score_diffs=%d)" % (
              entry, flips_before, flips_after, improved, len(regressions),
              spec_pass, flips_match, len(score_diffs)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
