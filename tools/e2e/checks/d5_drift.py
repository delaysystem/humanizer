"""D5 E2E-1b (independent path): regeneration drift — fresh Bodhan calls on
the frozen drift sample, compared to frozen variants (fidelity of regen vs
frozen text + overall-score deltas) against frozen thresholds. The pure
truncate condition must regenerate byte-identically (our-code determinism).
A threshold trip fails unless build/evidence/D5/external-changes.json
documents an external cause covering this run (human-attested); no file
exists by default, so undocumented drift is a failure, per the plan.
"""
import glob
import json
import os
import statistics
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg
import fidelity as fid


def main(run_dir, regen_root, d3_store, d3a_store, sample_path):
    report = {"check": "d5-drift", "pass": False, "details": []}
    d5 = cfg.load("d5.yaml")
    fid_mean_min = cfg.require_resolved(d5, "d5_regen_fidelity_mean_min", "config/d5.yaml")
    fid_min = cfg.require_resolved(d5, "d5_regen_fidelity_min", "config/d5.yaml")
    d_mean_max = cfg.require_resolved(d5, "d5_regen_score_delta_mean_max", "config/d5.yaml")
    d_max_max = cfg.require_resolved(d5, "d5_regen_score_delta_max_max", "config/d5.yaml")
    sample = json.load(open(sample_path))["sample"]
    model = fid.load_model()
    per_sample, byte_issues = [], []
    for pipe in sorted(sample):
        store_dir = d3a_store if pipe.startswith("d3a-") else d3_store
        regen_dir = os.path.join(regen_root, "regen-%s" % pipe)
        for sid in sorted(sample[pipe]):
            vid = "V-%s-%s" % (pipe, sid)
            frozen_text = open(os.path.join(store_dir, "variants", vid + ".txt")).read()
            regen_text = open(os.path.join(regen_dir, "variants", vid + ".txt")).read()
            if pipe == "cond-truncate-S":
                if regen_text != frozen_text:
                    byte_issues.append(vid)
                continue
            gate = fid.gate(frozen_text, regen_text, model=model)
            frozen_rec = json.load(open(os.path.join(store_dir, "records", vid + ".json")))
            regen_rec = json.load(open(os.path.join(regen_dir, "records", vid + ".json")))
            delta = abs(regen_rec["overall_verbatim"]["overall_score"]
                        - frozen_rec["overall_verbatim"]["overall_score"])
            per_sample.append({"variant_id": vid, "cosine": gate["cosine"],
                               "score_delta": delta})
    json.dump({"run_samples": per_sample, "truncate_byte_issues": byte_issues},
              open(os.path.join(run_dir, "drift-compare.json"), "w"), indent=2)
    if byte_issues:
        report["details"].append("truncate regen not byte-identical: %s" % byte_issues)
    if per_sample:
        cosines = [s["cosine"] for s in per_sample]
        deltas = [s["score_delta"] for s in per_sample]
        stats = {"n": len(per_sample), "fidelity_mean": statistics.mean(cosines),
                 "fidelity_min": min(cosines), "delta_mean": statistics.mean(deltas),
                 "delta_max": max(deltas)}
        json.dump(stats, open(os.path.join(run_dir, "drift-stats.json"), "w"), indent=2)
        trips = []
        if stats["fidelity_mean"] < fid_mean_min:
            trips.append("fidelity_mean %.4f < %.2f" % (stats["fidelity_mean"], fid_mean_min))
        if stats["fidelity_min"] < fid_min:
            trips.append("fidelity_min %.4f < %.2f" % (stats["fidelity_min"], fid_min))
        if stats["delta_mean"] > d_mean_max:
            trips.append("delta_mean %.2f > %.2f" % (stats["delta_mean"], d_mean_max))
        if stats["delta_max"] > d_max_max:
            trips.append("delta_max %.2f > %.2f" % (stats["delta_max"], d_max_max))
        if trips:
            cause_path = os.path.join(ROOT, "build", "evidence", "D5", "external-changes.json")
            cause = None
            if os.path.isfile(cause_path):
                for entry in json.load(open(cause_path)):
                    if entry.get("reviewed_by") and os.path.basename(run_dir) in entry.get(
                            "covers_runs", []):
                        cause = entry
            if cause is None:
                report["details"].append("UNDOCUMENTED DRIFT (failure): %s" % "; ".join(trips))
            else:
                report["details"].append("drift with documented cause (%s): %s"
                                         % (cause["source"], "; ".join(trips)))
        else:
            report["details"].append("%d regen samples: fidelity mean %.4f min %.4f, "
                                     "score-delta mean %.2f max %.2f — within bars"
                                     % (stats["n"], stats["fidelity_mean"],
                                        stats["fidelity_min"], stats["delta_mean"],
                                        stats["delta_max"]))
    report["pass"] = not [d for d in report["details"] if "within bars" not in d
                          and "documented cause" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d5-drift.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d5-drift: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]))
