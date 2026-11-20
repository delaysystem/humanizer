"""D4 E2E-1 (independent path): recompute every per-detector failure rate from
the frozen D3 + D3A stores with separate code and assert the analysis report
matches: fractions within d4_rate_tolerance, 1dp percentages within
percentage_recompute_rounding (this check validates that D0 row, as tasked).
Covers D3 AND D3A (the plan's D3-only wording predates D3A; D3A is the bulk
of the analysis and must not go unverified — documented in the verdict).
"""
import glob
import json
import math
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def _z_for(level):
    # Inverse-normal CDF via Acklam (separately written from the analyzer).
    p = 1.0 - (1.0 - level) / 2.0
    ca = [-39.69683028665376, 220.9460984245205, -275.9285104469687,
          138.3577518672690, -30.66479806614716, 2.506628277459239]
    cb = [-54.47609879822406, 161.585836580409, -155.6989798598866,
          66.80131188771972, -13.28068155288572]
    cc = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
          -2.549732539343734, 4.374664141464968, 2.938163982698783]
    cd = [0.007784695709041462, 0.3224671290700398, 2.445134137142996,
          3.754408661907416]
    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((cc[0] * q + cc[1]) * q + cc[2]) * q + cc[3]) * q + cc[4]) * q + cc[5]) / \
            ((((cd[0] * q + cd[1]) * q + cd[2]) * q + cd[3]) * q + 1.0)
    if p <= 0.97575:
        q, r = p - 0.5, (p - 0.5) ** 2
        return (((((ca[0] * r + ca[1]) * r + ca[2]) * r + ca[3]) * r + ca[4]) * r + ca[5]) * q / \
            (((((cb[0] * r + cb[1]) * r + cb[2]) * r + cb[3]) * r + cb[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((cc[0] * q + cc[1]) * q + cc[2]) * q + cc[3]) * q + cc[4]) * q + cc[5]) / \
        ((((cd[0] * q + cd[1]) * q + cd[2]) * q + cd[3]) * q + 1.0)


def _wilson(successes, trials, level):
    z = _z_for(level)
    p = successes / trials
    denom = 1.0 + z * z / trials
    mid = (p + z * z / (2.0 * trials)) / denom
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denom
    return max(0.0, mid - half), min(1.0, mid + half)


def main(run_dir, d3_store, d3a_store, orig_store, report_path):
    report = {"check": "d4-repro", "pass": False, "details": []}
    analysis = cfg.load("analysis.yaml")
    ai = set(analysis["flip_verdict_map_ai"])
    human = set(analysis["flip_verdict_map_human"])
    level = cfg.require_resolved(analysis, "analysis_ci_level", "config/analysis.yaml")
    tols = cfg.load("tolerances.yaml")
    tol_frac = cfg.require_resolved(tols, "d4_rate_tolerance", "config/tolerances.yaml")
    tol_pct = cfg.require_resolved(tols, "percentage_recompute_rounding",
                                   "config/tolerances.yaml")
    inv = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json")))["payload"]["detectors"]
    names = [d["name"] for d in inv]
    originals = {}
    for path in glob.glob(os.path.join(orig_store, "records", "*.json")):
        rec = json.load(open(path))
        originals[rec["sample_id"]] = rec["per_detector_scores"]
    frozen = json.load(open(report_path))
    checked = 0
    for store_dir in (d3_store, d3a_store):
        grouped = {}
        for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
            rec = json.load(open(path))
            grouped.setdefault(rec["condition_id"], []).append(rec)
        for condition in sorted(grouped):
            variants = grouped[condition]
            passing = [v for v in variants if v["fidelity"]["fidelity_passing"]]
            base = sorted({v["original_id"] for v in variants})
            expect = frozen["conditions"][condition]["detectors"]
            if frozen["conditions"][condition]["passing_n"] != len(passing):
                report["details"].append("%s: passing_n drift" % condition)
            for name in names:
                exp = expect[name]
                flips = sum(1 for v in passing
                            if originals[v["original_id"]][name]["verdict"] in ai
                            and v["per_detector_scores"][name]["verdict"] in human)
                n = len(passing)
                if exp["n"] != n or exp["flips"] != flips:
                    report["details"].append("%s %s: n/flips drift" % (condition, name))
                    continue
                lo, hi = _wilson(flips, n, level)
                pairs = [("flip_rate", flips / n), ("flip_ci95[0]", lo), ("flip_ci95[1]", hi)]
                dv = sum(1 for v in passing
                         if v["per_detector_scores"][name]["verdict"] in ai)
                db = sum(1 for s in base if originals[s][name]["verdict"] in ai)
                dv_lo, dv_hi = _wilson(dv, n, level)
                db_lo, db_hi = _wilson(db, len(base), level)
                pairs += [("detection_variant", dv / n), ("detection_baseline", db / len(base)),
                          ("detection_delta", dv / n - db / len(base))]
                got = {"flip_rate": exp["flip_rate"], "flip_ci95[0]": exp["flip_ci95"][0],
                       "flip_ci95[1]": exp["flip_ci95"][1],
                       "detection_variant": exp["detection_variant"],
                       "detection_baseline": exp["detection_baseline"],
                       "detection_delta": exp["detection_delta"]}
                for key, mine in pairs:
                    if abs(got[key] - round(mine, 4)) > tol_frac:
                        report["details"].append("%s %s: %s drift" % (condition, name, key))
                for key, mine in [("detection_variant_ci95[0]", dv_lo),
                                  ("detection_variant_ci95[1]", dv_hi),
                                  ("detection_baseline_ci95[0]", db_lo),
                                  ("detection_baseline_ci95[1]", db_hi)]:
                    outer, idx = key[:-3], int(key[-2])
                    if abs(exp[outer][idx] - round(mine, 4)) > tol_frac:
                        report["details"].append("%s %s: %s drift" % (condition, name, key))
                if abs(exp["flip_rate_pct"] - round(100.0 * flips / n, 1)) > tol_pct:
                    report["details"].append("%s %s: pct drift" % (condition, name))
                checked += 1
    if not report["details"]:
        report["details"].append("%d cells recomputed: fractions within %s, pcts within %s"
                                 % (checked, tol_frac, tol_pct))
    report["pass"] = not [d for d in report["details"] if "recomputed" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d4-repro.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d4-repro: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]))
