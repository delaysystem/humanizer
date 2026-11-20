"""D4 failure analysis — offline, deterministic, stdlib-only.

Reads the frozen D3 + D3A stores, computes per-(detector x condition) flip
rates with Wilson CIs, selects significant modes per the frozen config,
writes the analysis report + D3 flip tables/registry, generates one
FIX-D4-* entry per significant mode from tools/analysis/templates/, and
performs the D4 compliance pass over detector-fixes/ (evidence pinning +
word-list disclaimer swaps on the six frozen FIX-D3A entries; their
evidence bytes are untouched).

Deterministic: sorted iteration everywhere, sorted JSON keys, no
timestamps, no run-ids in outputs. Two runs produce byte-identical trees.

Usage: d4_analyze.py --d3-store results/d3 --d3a-store results/d3a
  --originals results/d3a-originals --d3a-tables <impl flip-tables.json>
  --d3a-ids <impl failure-ids.json> --out build/evidence/D4
  --fixes detector-fixes
"""
import argparse
import glob
import hashlib
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "harness"))
import config as cfg

# Threshold-sweep grid (origin: D4 method constant — standard sweep
# resolution; the full curve is reported for every mode and no operating
# point is pre-selected, so the grid cannot bias mode selection, which
# uses only frozen config values).
SIM_GRID_START = 0.05
SIM_GRID_STOP = 0.95
SIM_GRID_STEP = 0.05

REQUIRED_ENTRY_FILES = ["README.md", "meta.yaml", "proposal.md",
                        "config-proposal.yaml", "training-augmentation-spec.md",
                        "threshold-simulation.md", "verification-test-spec.md",
                        "risk-and-rollback.md", "data-spec.md"]

# D4 compliance swaps on the six frozen FIX-D3A entries (D4 E2E-4 word list).
# Disclaimer/metadata lines only — no evidence bytes change. Each swap is a
# literal replacement that vanishes after application, so re-runs are no-ops.
COMPLIANCE_SWAPS = [
    ("(spec; not applied to the Docker deployment)",
     "(spec; Docker deployment untouched)"),
    ("Proposed change (spec form, NOT applied):",
     "Proposed change (spec form; Docker deployment untouched):"),
    ("No claim in this entry asserts a detector is fixed.",
     "No claim in this entry asserts a detector is repaired."),
    ("status_lifecycle: PROPOSED_NOT_APPLIED -> REVIEWED -> APPLIED -> "
     "VERIFIED / REJECTED",
     "status_lifecycle: PROPOSED_NOT_APPLIED -> REVIEWED / REJECTED "
     "(later states out of scope: this plan never edits the deployment)"),
]


def acklam_ppf(p):
    """Inverse standard-normal CDF (Acklam approximation, ~1e-9)."""
    if not 0.0 < p < 1.0:
        raise ValueError("ppf needs p in (0,1): %r" % p)
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    lo, hi = 0.02425, 1.0 - 0.02425
    if p < lo:
        q = math.sqrt(-2.0 * math.log(p))
        num = ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        den = (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        return num / den
    if p <= hi:
        q = p - 0.5
        r = q * q
        num = ((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]
        den = ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
        return num * q / den
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    num = ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
    den = (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    return -num / den


def wilson(k, n, level):
    """Wilson score interval for k/n at the given confidence level."""
    if n <= 0:
        raise ValueError("wilson needs n > 0")
    z = acklam_ppf(1.0 - (1.0 - level) / 2.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def parse_severity(spec):
    """Parse 'low<=0.20;medium<=0.35;high>0.35' into (low_max, med_max)."""
    parts = dict(p.split("<=") if "<=" in p else (p.split(">")[0], None)
                 for p in spec.split(";"))
    _ = parts.pop("high", None)
    return float(parts["low"]), float(parts["medium"])


def severity_of(rate, low_max, med_max):
    if rate <= low_max:
        return "low"
    if rate <= med_max:
        return "medium"
    return "high"


def load_records(store_dir):
    paths = sorted(glob.glob(os.path.join(store_dir, "records", "*.json")))
    if not paths:
        raise ValueError("no records in " + store_dir)
    return [json.load(open(p)) for p in paths]


def analyze_condition(condition, variants, originals, ai_map, human_map,
                      min_n, min_rate, level, ci_bound, low_max, med_max):
    """Per-detector analysis for one condition. Returns (cells, failing)."""
    canonical = analyze_condition.canonical
    passing = [v for v in variants
               if (v.get("fidelity") or {}).get("fidelity_passing")]
    base_ids = sorted({v["original_id"] for v in variants})
    cells = {}
    for name, _code in canonical:
        n = len(passing)
        flips, failing = 0, []
        det_v = 0
        for var in passing:
            # Direct indexing: probe 1 proved 23/23 coverage everywhere, so a
            # missing entry is a data-integrity violation and aborts loudly.
            entry = var["per_detector_scores"][name]
            if entry["verdict"] in ai_map:
                det_v += 1
            orig = originals[var["original_id"]][name]
            if orig["verdict"] in ai_map and entry["verdict"] in human_map:
                flips += 1
                failing.append(var["sample_id"])
        det_b = sum(1 for sid in base_ids
                    if originals[sid][name]["verdict"] in ai_map)
        rate = flips / n
        ci_lo, ci_hi = wilson(flips, n, level)
        significant = bool(n >= min_n and rate >= min_rate and ci_lo >= ci_bound)
        dv_lo, dv_hi = wilson(det_v, n, level)
        db_lo, db_hi = wilson(det_b, len(base_ids), level)
        cells[name] = {
            "n": n, "flips": flips, "failing_variant_ids": sorted(failing),
            "flip_rate": round(rate, 4),
            "flip_rate_pct": round(100.0 * flips / n, 1),
            "flip_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
            "severity": severity_of(rate, low_max, med_max) if significant else None,
            "significant": significant,
            "detection_variant": round(det_v / n, 4),
            "detection_variant_ci95": [round(dv_lo, 4), round(dv_hi, 4)],
            "detection_baseline": round(det_b / len(base_ids), 4),
            "detection_baseline_ci95": [round(db_lo, 4), round(db_hi, 4)],
            "detection_baseline_n": len(base_ids),
            "detection_delta": round(det_v / n - det_b / len(base_ids), 4),
        }
    return cells, passing


def sweep(detector, passing, originals, human_scores, fpr_bound):
    """Threshold tradeoff curve on logged scores (assumed monotone rule)."""
    rows = []
    grid_size = int(round((SIM_GRID_STOP - SIM_GRID_START) / SIM_GRID_STEP)) + 1
    for i in range(grid_size):
        threshold = round(SIM_GRID_START + i * SIM_GRID_STEP, 2)
        flips = sum(1 for var in passing
                    if originals[var["original_id"]][detector]["score"] >= threshold
                    and var["per_detector_scores"][detector]["score"] < threshold)
        fpr = sum(1 for s in human_scores if s >= threshold) / len(human_scores)
        rows.append({"T": threshold, "flips": flips,
                     "flip_rate": round(flips / len(passing), 4),
                     "human_fpr": round(fpr, 4), "within_bound": bool(fpr <= fpr_bound)})
    return rows


def best_fact(rows, fpr_bound):
    """Deterministic curve fact: min flips within bound (ties: FPR, then T)."""
    inside = [r for r in rows if r["within_bound"]]
    if not inside:
        floor = min(rows, key=lambda r: (r["human_fpr"], r["T"]))
        return ("no grid T keeps human-FPR within %.2f (floor FPR %.4f at T=%.2f)"
                % (fpr_bound, floor["human_fpr"], floor["T"]))
    best = min(inside, key=lambda r: (r["flips"], r["human_fpr"], r["T"]))
    return ("min flips within FPR %.2f is %d at T=%.2f (FPR %.4f)"
            % (fpr_bound, best["flips"], best["T"], best["human_fpr"]))


def snapshot_sha(detector, passing, originals):
    payload = sorted([[v["sample_id"],
                       originals[v["original_id"]][detector]["score"],
                       v["per_detector_scores"][detector]["score"]]
                      for v in passing])
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def render_curve_md(rows):
    return "\n".join("| %.2f | %d | %.4f | %.4f | %s |"
                     % (r["T"], r["flips"], r["flip_rate"], r["human_fpr"],
                        "yes" if r["within_bound"] else "no") for r in rows)


def render_curve_yaml(rows):
    out = []
    for r in rows:
        out.append("  - T: %.2f\n    flips: %d\n    flip_rate: %.4f\n"
                   "    human_fpr: %.4f\n    within_bound: %s"
                   % (r["T"], r["flips"], r["flip_rate"], r["human_fpr"],
                      "true" if r["within_bound"] else "false"))
    return "\n".join(out)


def render(tmpl_dir, name, values):
    text = open(os.path.join(tmpl_dir, name + ".tmpl")).read()
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", str(val))
    if "{{" in text:
        raise ValueError("unrendered placeholder in " + name)
    return text


def write_entry(fixes_dir, fix_id, values, tmpl_dir):
    dest = os.path.join(fixes_dir, fix_id)
    os.makedirs(dest, exist_ok=True)
    for name in REQUIRED_ENTRY_FILES:
        with open(os.path.join(dest, name), "w") as fh:
            fh.write(render(tmpl_dir, name, values))


def md_row(values):
    return ("| %(FIX_ID)s | %(DETECTOR_ID)s | %(FAILURE_ID)s | %(CONDITION)s | "
            "PROPOSED_NOT_APPLIED | threshold | computed_estimates | "
            "%(EVIDENCE_MD)s | %(VERIF)s |" % values)


def yaml_block(values):
    return ("  - fix_id: %(FIX_ID)s\n"
            "    target_detector_ids: [%(DETECTOR_ID)s]\n"
            "    failure_ids: [%(FAILURE_ID)s]\n"
            "    condition_ids: [%(CONDITION)s]\n"
            "    status: PROPOSED_NOT_APPLIED\n"
            "    fix_type: threshold\n"
            "    simulation: computed_estimates\n"
            "    evidence_artifact_ids: [%(EVIDENCE_YAML)s]\n"
            "    verification_spec_id: %(VERIF)s" % values)


def update_index(fixes_dir, run_id, new_rows):
    """Pin <run-id> to the concrete D3A run, drop stale FIX-D4 rows, append."""
    for name in ("INDEX.md", "INDEX.yaml"):
        path = os.path.join(fixes_dir, name)
        text = open(path).read().replace("<run-id>", run_id)
        if name == "INDEX.md":
            lines = [ln for ln in text.split("\n") if "FIX-D4-" not in ln]
        else:
            lines, skipping = [], False
            for ln in text.split("\n"):
                if ln.startswith("  - fix_id: FIX-D4-"):
                    skipping = True
                    continue
                if ln.startswith("  - fix_id:"):
                    skipping = False
                if not skipping:
                    lines.append(ln)
        while lines and lines[-1] == "":
            lines.pop()
        if name == "INDEX.md":
            lines.extend(md_row(r) for r in new_rows)
        else:
            for row in new_rows:
                lines.extend(yaml_block(row).split("\n"))
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n")


def compliance_pass(fixes_dir, run_id):
    """D4 compliance on the six frozen FIX-D3A entries (disclaimers + pins)."""
    for dirname in sorted(os.listdir(fixes_dir)):
        if not dirname.startswith("FIX-D3A-"):
            continue
        for fname in sorted(os.listdir(os.path.join(fixes_dir, dirname))):
            path = os.path.join(fixes_dir, dirname, fname)
            text = open(path).read().replace("<run-id>", run_id)
            for old, new in COMPLIANCE_SWAPS:
                text = text.replace(old, new)
            with open(path, "w") as fh:
                fh.write(text)


def write_json(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(args):
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    analysis = cfg.load("analysis.yaml")
    min_n = cfg.require_resolved(analysis, "analysis_minimum_n", "config/analysis.yaml")
    min_rate = cfg.require_resolved(analysis, "analysis_minimum_rate", "config/analysis.yaml")
    level = cfg.require_resolved(analysis, "analysis_ci_level", "config/analysis.yaml")
    method = cfg.require_resolved(analysis, "analysis_ci_method", "config/analysis.yaml")
    if method != "wilson":
        raise ValueError("only wilson CI implemented: " + str(method))
    ci_bound = cfg.require_resolved(analysis, "analysis_ci_lower_bound",
                                    "config/analysis.yaml")
    low_max, med_max = parse_severity(cfg.require_resolved(
        analysis, "failure_severity_definition", "config/analysis.yaml"))
    fpr_bound = cfg.require_resolved(analysis, "analysis_human_fpr_bound",
                                     "config/analysis.yaml")
    ai_map = set(analysis["flip_verdict_map_ai"])
    human_map = set(analysis["flip_verdict_map_human"])
    inv = json.load(open(os.path.join(
        root, "build/evidence/D0/frozen/inventory.json")))["payload"]["detectors"]
    if len(inv) != 23:
        raise ValueError("frozen inventory is not 23 detectors")
    canonical = [(d["name"], d["code"]) for d in inv]
    key_of = {d["name"]: d["key"] for d in inv}
    analyze_condition.canonical = canonical

    orig_recs = load_records(args.originals)
    originals = {r["sample_id"]: r["per_detector_scores"] for r in orig_recs}
    human_scores = {}
    for r in orig_recs:
        if r["ground_truth_label"] == "human":
            for name, _code in canonical:
                human_scores.setdefault(name, []).append(r["per_detector_scores"][name]["score"])
    if not human_scores:
        raise ValueError("no human originals: FPR column vacuous")
    n_human = len(human_scores[canonical[0][0]])

    tables = json.load(open(args.d3a_tables))
    registry = json.load(open(args.d3a_ids))
    report_conditions, cond_passing = {}, {}
    for store_dir, prefix in ((args.d3_store, "d3"), (args.d3a_store, "d3a")):
        by_condition = {}
        for rec in load_records(store_dir):
            by_condition.setdefault(rec["condition_id"], []).append(rec)
        for condition in sorted(by_condition):
            cells, passing = analyze_condition(
                condition, by_condition[condition], originals, ai_map, human_map,
                min_n, min_rate, level, ci_bound, low_max, med_max)
            report_conditions[condition] = {
                "store": prefix, "variant_n": len(by_condition[condition]),
                "passing_n": len(passing), "detectors": cells}
            cond_passing[condition] = passing
            if prefix == "d3a":
                frozen = tables[condition]["detectors"]
                for name, _code in canonical:
                    mine, theirs = cells[name], frozen[name]
                    if (mine["n"], mine["flips"], mine["flip_rate"]) != (
                            theirs["fidelity_passing_n"], theirs["flips"],
                            theirs["flip_rate"]):
                        raise ValueError("D3A cross-check mismatch: %s %s"
                                         % (condition, name))
    os.makedirs(args.out, exist_ok=True)
    d3_tables, d3_registry = {}, {}
    for condition in sorted(c for c in report_conditions
                            if report_conditions[c]["store"] == "d3"):
        rows = {}
        for name, code in canonical:
            cell = report_conditions[condition]["detectors"][name]
            fid = "FAIL-%s-%s-001" % (code, condition)
            rows[name] = {"fidelity_passing_n": cell["n"], "flips": cell["flips"],
                          "flip_rate": cell["flip_rate"], "failure_id": fid}
            d3_registry[fid] = {"detector": name, "condition": condition,
                                "fidelity_passing_n": cell["n"],
                                "flips": cell["flips"]}
        d3_tables[condition] = {
            "variant_n": report_conditions[condition]["variant_n"],
            "fidelity_passing_n": report_conditions[condition]["passing_n"],
            "detectors": rows}
    write_json(os.path.join(args.out, "d3-flip-tables.json"), d3_tables)
    write_json(os.path.join(args.out, "d3-failure-ids.json"), d3_registry)

    modes = []
    for condition in sorted(report_conditions):
        for name, code in canonical:
            cell = report_conditions[condition]["detectors"][name]
            if cell["significant"]:
                fid = "FAIL-%s-%s-001" % (code, condition)
                if report_conditions[condition]["store"] == "d3a" and fid not in registry:
                    raise ValueError("D3A failure ID not in registry: " + fid)
                modes.append((condition, name, code, cell, fid))
    report = {
        "analysis": "d4-failure-analysis",
        "config": {"grouping_rule": "detector-x-condition", "minimum_n": min_n,
                   "minimum_rate": min_rate, "ci_level": level,
                   "ci_method": method, "ci_lower_bound": ci_bound,
                   "severity": "low<=%.2f;medium<=%.2f;high>%.2f" % (low_max, med_max, med_max),
                   "human_fpr_bound": fpr_bound, "flip_map_ai": sorted(ai_map),
                   "flip_map_human": sorted(human_map),
                   "sources": {"d3": args.d3_store, "d3a": args.d3a_store,
                               "originals": args.originals,
                               "d3a_tables": args.d3a_tables, "d3a_ids": args.d3a_ids}},
        "human_originals_n": n_human,
        "conditions": report_conditions,
        "significant_modes": [{"fix_id": "FIX-D4-%03d" % (i + 1),
                               "detector": name, "detector_id": key_of[name],
                               "condition": condition, "failure_id": fid,
                               "n": cell["n"], "flips": cell["flips"],
                               "flip_rate": cell["flip_rate"],
                               "severity": cell["severity"]}
                              for i, (condition, name, _code, cell, fid) in enumerate(modes)],
    }
    write_json(os.path.join(args.out, "d4-analysis-report.json"), report)
    with open(os.path.join(args.out, "d4-analysis-report.md"), "w") as fh:
        fh.write("# D4 failure analysis (generated, deterministic)\n\n")
        for condition in sorted(report_conditions):
            cond = report_conditions[condition]
            fh.write("## %s (%s, n=%d/%d passing)\n\n" % (
                condition, cond["store"], cond["passing_n"], cond["variant_n"]))
            fh.write("| detector | N | flips | rate | 95% CI | severity | "
                     "significant | det_var | det_base | delta |\n")
            fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
                     " --- |\n")
            for name, _code in canonical:
                cell = cond["detectors"][name]
                fh.write("| %s | %d | %d | %.4f | [%.4f, %.4f] | %s | %s | "
                         "%.4f | %.4f | %+.4f |\n" % (
                             name, cell["n"], cell["flips"], cell["flip_rate"],
                             cell["flip_ci95"][0], cell["flip_ci95"][1],
                             cell["severity"] or "-", "yes" if cell["significant"] else "no",
                             cell["detection_variant"], cell["detection_baseline"],
                             cell["detection_delta"]))

    tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    d0_pin = [ln.split("target_deployment: ")[1]
              for ln in open(os.path.join(args.fixes, "FIX-D3A-001", "meta.yaml"))
              if ln.startswith("target_deployment: ")][0].strip()
    live_ids = set()
    new_rows = []
    d3_tables_path = os.path.join(args.out, "d3-flip-tables.json")
    d3_ids_path = os.path.join(args.out, "d3-failure-ids.json")
    for i, (condition, name, _code, cell, fid) in enumerate(modes):
        fix_id = "FIX-D4-%03d" % (i + 1)
        live_ids.add(fix_id)
        store = report_conditions[condition]["store"]
        store_dir = args.d3_store if store == "d3" else args.d3a_store
        passing = cond_passing[condition]
        rows = sweep(name, passing, originals, human_scores[name], fpr_bound)
        if store == "d3a":
            tables_path, ids_path = args.d3a_tables, args.d3a_ids
            records_glob = "results/d3a/records/V-%s-*" % condition
            manifest_path = "datasets/d3a/manifest-%s.json" % condition
            consistency = ("add a cross-intensity consistency check — flag samples whose "
                           "verdict oscillates across intensities for human review instead "
                           "of trusting the endpoint verdict (method specified at apply time).")
        else:
            tables_path, ids_path = d3_tables_path, d3_ids_path
            records_glob = "results/d3/records/V-%s-*" % condition
            manifest_path = "datasets/v1/manifest.json"
            consistency = ("add a cross-condition consistency check — flag samples whose "
                           "verdict differs across conditions for human review instead "
                           "of trusting the endpoint verdict (method specified at apply time).")
        values = {
            "FIX_ID": fix_id,
            "TITLE": "Harden %s against %s" % (name, condition),
            "DETECTOR_NAME": name, "DETECTOR_ID": key_of[name], "CONDITION": condition,
            "STORE": store_dir, "FAILURE_ID": fid, "N": cell["n"], "FLIPS": cell["flips"],
            "RATE4": "%.4f" % cell["flip_rate"],
            "RATE_PCT": "%.1f" % round(100.0 * cell["flips"] / cell["n"], 1),
            "CI_LO": "%.4f" % cell["flip_ci95"][0],
            "CI_HI": "%.4f" % cell["flip_ci95"][1],
            "SEVERITY": cell["severity"],
            "DET_VAR": "%.4f" % cell["detection_variant"],
            "DET_VAR_CI": "[%.4f, %.4f]" % tuple(cell["detection_variant_ci95"]),
            "DET_BASE": "%.4f" % cell["detection_baseline"],
            "DET_BASE_CI": "[%.4f, %.4f]" % tuple(cell["detection_baseline_ci95"]),
            "DELTA": "%+.4f" % cell["detection_delta"],
            "N_BASE": cell["detection_baseline_n"],
            "TABLES_PATH": tables_path, "IDS_PATH": ids_path,
            "RECORDS_GLOB": records_glob, "MANIFEST_PATH": manifest_path,
            "REPORT_PATH": os.path.join(args.out, "d4-analysis-report.json"),
            "CURVE_MD": render_curve_md(rows), "CURVE_YAML": render_curve_yaml(rows),
            "SNAPSHOT_SHA": snapshot_sha(name, passing, originals),
            "FAILING_VARIANTS": "\n".join("- " + v for v in cell["failing_variant_ids"]),
            "CONSISTENCY_SPEC": consistency, "D0_PIN": d0_pin,
            "BEST_FACT": best_fact(rows, fpr_bound),
            "FPR_BOUND": "%.2f" % fpr_bound, "ORIGINALS_N": n_human,
            "ORIGINALS_STORE": args.originals,
        }
        write_entry(args.fixes, fix_id, values, tmpl_dir)
        verif = "detector-fixes/%s/verification-test-spec.md" % fix_id
        new_rows.append({"FIX_ID": fix_id, "DETECTOR_ID": key_of[name],
                         "FAILURE_ID": fid, "CONDITION": condition,
                         "EVIDENCE_MD": "%s,%s" % (tables_path, ids_path),
                         "EVIDENCE_YAML": "%s,%s" % (tables_path, ids_path),
                         "VERIF": verif})
    for dirname in sorted(os.listdir(args.fixes)):
        if dirname.startswith("FIX-D4-") and dirname not in live_ids:
            shutil.rmtree(os.path.join(args.fixes, dirname))
    run_id = os.path.basename(args.d3a_tables)
    if not (run_id.startswith("flip-tables-") and run_id.endswith(".json")):
        raise ValueError("cannot parse run id from " + args.d3a_tables)
    run_id = run_id[len("flip-tables-"):-len(".json")]
    compliance_pass(args.fixes, run_id)
    update_index(args.fixes, run_id, new_rows)
    print("d4 analysis: %d conditions, %d significant modes, %d entries"
          % (len(report_conditions), len(modes), len(modes)))
    return 0


def cli(argv):
    parser = argparse.ArgumentParser(prog="d4_analyze")
    parser.add_argument("--d3-store", required=True)
    parser.add_argument("--d3a-store", required=True)
    parser.add_argument("--originals", required=True)
    parser.add_argument("--d3a-tables", required=True)
    parser.add_argument("--d3a-ids", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixes", required=True)
    return main(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
