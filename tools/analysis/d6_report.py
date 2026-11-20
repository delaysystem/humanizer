"""D6 final-report generator — every number tagged, every claim artifact-backed.

Reads frozen stores/config/verdicts/evidence and writes the final report plus
machine tables. Deterministic: no timestamps, no run IDs, sorted iteration,
fixed float formats. Static prose carries no digit-written values except
trace tags, code spans (identifiers), and reference shapes (section/milestone
IDs); every measured or configured value is a [value](#num-<id>) tag with a
traceability row. Report prose avoids the evasion-word and recommendation
lists (see the D5 gate config); blocked-item excerpts render as blockquotes
(verbatim verdict citations, verified by the blocked-items check).
Usage: d6_report.py --out <build/evidence/D6> --report <build/FINAL-REPORT.md>
"""
import argparse
import glob
import hashlib
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402 — harness loader lives beside this module

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)


def load_json(rel):
    with open(os.path.join(ROOT, rel)) as fh:
        return json.load(fh)


def store_records(store):
    paths = sorted(glob.glob(os.path.join(ROOT, store, "records", "*.json")))
    if not paths:
        raise ValueError("no records in " + store)
    return [load_json(os.path.relpath(p, ROOT)) for p in paths]


class Report(object):
    def __init__(self):
        self.d6 = cfg.load("d6.yaml")
        self.analysis = cfg.load("analysis.yaml")
        self.tols = cfg.load("tolerances.yaml")
        self.reporting = cfg.load("reporting.yaml")
        self.pipes = cfg.load("pipelines.yaml")
        self.numbers = []
        self.seen = {}

    # -- trace tagging -----------------------------------------------------
    def tag(self, number_id, value, artifact_id, recomputation, tolerance,
            notes=""):
        text = str(value)
        if number_id in self.seen:
            if self.seen[number_id] != text:
                raise ValueError("conflicting values for " + number_id)
        else:
            self.seen[number_id] = text
            tol_name, tol_val = tolerance
            self.numbers.append({
                "number_id": number_id, "value_as_reported": text,
                "artifact_id": artifact_id, "recomputation": recomputation,
                "tolerance_name": tol_name, "tolerance_value": tol_val,
                "notes": notes})
        return "[%s](#num-%s)" % (text, number_id)

    def recompute_cmd(self, number_id):
        return "python3 tools/analysis/d6_recompute.py %s" % number_id

    def pct(self):
        return cfg.require_resolved(self.d6, "d6_pct_decimals", "config/d6.yaml")

    def frac(self):
        return cfg.require_resolved(self.d6, "d6_frac_decimals", "config/d6.yaml")

    def fmt_pct(self, part, whole):
        return "%.*f" % (self.pct(), 100.0 * part / whole) if whole else "0.0"

    def fmt_frac(self, value):
        return "%.*f" % (self.frac(), value)

    def pct_tol(self):
        return ("percentage_recompute_rounding", cfg.require_resolved(
            self.tols, "percentage_recompute_rounding", "config/tolerances.yaml"))

    # -- inputs ------------------------------------------------------------
    def pipeline_order(self):
        order = list(self.pipes["dataset_pipelines"]) + list(self.pipes["d3a_pipelines"])
        return order

    def detectors(self):
        inv = load_json("build/evidence/D0/frozen/inventory.json")["payload"]["detectors"]
        return [(d["name"], d["key"], d["detector_type"]) for d in inv]

    def step_refs(self, pipe_id):
        return list(cfg.require_resolved(
            self.pipes, "pipeline_%s_steps" % pipe_id, "config/pipelines.yaml"))

    def manifest_for(self, pipe_id):
        if pipe_id.startswith("d3a-"):
            return load_json("datasets/d3a/manifest-%s.json" % pipe_id)
        sel = cfg.require_resolved(
            self.pipes, "pipeline_%s_samples" % pipe_id, "config/pipelines.yaml")
        return {"manifest": "datasets/v1/manifest.json", "selector": sel,
                "note": "D3 conditions draw from v1 directly (no per-condition manifest)"}

    def config_hash(self, pipe_id):
        refs = self.step_refs(pipe_id)
        params = {}
        for ref in refs:
            name, _at, _ver = ref.partition("@")
            mod_key = "step_%s_%s_module" % (name, _ver)
            _mod = cfg.require_resolved(self.pipes, mod_key, "config/pipelines.yaml")
            par_key = "step_%s_%s_params" % (name, _ver)
            par_file = cfg.require_resolved(self.pipes, par_key, "config/pipelines.yaml")
            params[ref] = cfg.load(par_file)
        manifest = dict(self.manifest_for(pipe_id))
        manifest.pop("producing_run_id", None)
        canonical = json.dumps({"pipeline_id": pipe_id, "steps": refs,
                                "step_params": params,
                                "dataset_manifest": manifest}, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # -- buckets -----------------------------------------------------------
    def buckets(self):
        ai = set(self.analysis["flip_verdict_map_ai"])
        human = set(self.analysis["flip_verdict_map_human"])
        neither = set(self.analysis["flip_verdict_map_neither"])
        overall = {
            "ai": set(self.d6["d6_overall_bucket_ai"]),
            "human": set(self.d6["d6_overall_bucket_human"]),
            "uncertain": set(self.d6["d6_overall_bucket_uncertain"])}
        return ai, human, neither, overall

    def load_all(self):
        d3 = store_records("results/d3")
        d3a = store_records("results/d3a")
        originals = {}
        for rec in store_records("results/d3a-originals"):
            originals[rec["sample_id"]] = rec
        d2 = store_records("results/d2")
        return d3, d3a, originals, d2

    def evidence_ids(self, variants):
        return sorted("results/%s/records/%s.json" % (
            "d3a" if v["condition_id"].startswith("d3a-") else "d3",
            v["sample_id"]) for v in variants)

    # -- per-pipeline + detail + unfiltered --------------------------------
    def build_tables(self, variants_by_pipe, originals):
        ai, human, neither, overall = self.buckets()
        low_n = cfg.require_resolved(self.reporting, "reporting_low_n_minimum",
                                     "config/reporting.yaml")
        unc_basis = cfg.require_resolved(self.d6, "d6_uncertain_basis", "config/d6.yaml")
        per_pipe, per_det, unfiltered = [], [], []
        raw_by_pipe = {}
        det_info = self.detectors()
        for pipe in self.pipeline_order():
            variants = variants_by_pipe.get(pipe, [])
            if not variants:
                raise ValueError("pipeline %s has no variants in stores" % pipe)
            passing = [v for v in variants
                       if (v.get("fidelity") or {}).get("fidelity_passing")]
            total, n_pass = len(variants), len(passing)
            cos = sorted((v["fidelity"]["cosine"] for v in passing))
            median = statistics.median(cos)
            spread = max(cos) - min(cos)
            o_counts = {"ai": 0, "human": 0, "uncertain": 0}
            raw_counts = {}
            for v in passing:
                verdict = (v.get("overall_verbatim") or {})["overall_verdict"]
                raw_counts[verdict] = raw_counts.get(verdict, 0) + 1
                placed = False
                for bucket, values in overall.items():
                    if verdict in values:
                        o_counts[bucket] += 1
                        placed = True
                if not placed:
                    raise ValueError("unmapped overall verdict %r" % verdict)
            raw_by_pipe[pipe] = dict(raw_counts)
            refs = self.step_refs(pipe)
            steps = [{"name": r.partition("@")[0], "version": r.partition("@")[2]}
                     for r in refs]
            row = {
                "pipeline_id": pipe, "config_hash": self.config_hash(pipe),
                "steps": steps, "total_samples_N": total,
                "fidelity_passing_N": n_pass,
                "fidelity_passing_rate": round(n_pass / total, 4),
                "overall_human_pct": float(self.fmt_pct(o_counts["human"], n_pass)),
                "overall_ai_pct": float(self.fmt_pct(o_counts["ai"], n_pass)),
                "overall_uncertain_pct": float(self.fmt_pct(o_counts["uncertain"], n_pass)),
                "overall_basis": "sloptotal_combined_verbatim",
                "fidelity_median": round(median, 4),
                "fidelity_spread": round(spread, 4),
                "spot_check_pass_rate": None, "spot_check_N": 0,
                "low_N_flag": bool(n_pass < low_n),
                "evidence_artifact_ids": self.evidence_ids(passing)}
            per_pipe.append(row)
            u_counts = {"ai": 0, "human": 0, "uncertain": 0}
            u_cos = sorted(v["fidelity"]["cosine"] for v in variants)
            for v in variants:
                verdict = (v.get("overall_verbatim") or {})["overall_verdict"]
                for bucket, values in overall.items():
                    if verdict in values:
                        u_counts[bucket] += 1
            u_row = {"pipeline_id": pipe}
            for key in ("config_hash", "total_samples_N", "fidelity_passing_N",
                        "fidelity_passing_rate", "overall_human_pct",
                        "overall_ai_pct", "overall_uncertain_pct", "overall_basis",
                        "fidelity_median", "fidelity_spread",
                        "spot_check_pass_rate", "spot_check_N", "low_N_flag"):
                u_row[key + "_unfiltered"] = None
            u_row["steps_unfiltered"] = steps
            u_row["config_hash_unfiltered"] = row["config_hash"]
            u_row["total_samples_N_unfiltered"] = total
            u_row["fidelity_passing_N_unfiltered"] = n_pass
            u_row["fidelity_passing_rate_unfiltered"] = round(n_pass / total, 4)
            u_row["overall_basis_unfiltered"] = "sloptotal_combined_verbatim"
            u_row["overall_human_pct_unfiltered"] = float(self.fmt_pct(u_counts["human"], total))
            u_row["overall_ai_pct_unfiltered"] = float(self.fmt_pct(u_counts["ai"], total))
            u_row["overall_uncertain_pct_unfiltered"] = float(
                self.fmt_pct(u_counts["uncertain"], total))
            u_row["fidelity_median_unfiltered"] = round(statistics.median(u_cos), 4)
            u_row["fidelity_spread_unfiltered"] = round(max(u_cos) - min(u_cos), 4)
            u_row["spot_check_pass_rate_unfiltered"] = None
            u_row["spot_check_N_unfiltered"] = 0
            u_row["low_N_flag_unfiltered"] = bool(total < low_n)
            u_row["evidence_artifact_ids_unfiltered"] = self.evidence_ids(variants)
            unfiltered.append(u_row)
            for name, _key, dtype in det_info:
                counts = {"ai": 0, "human": 0, "uncertain": 0}
                for v in passing:
                    verdict = v["per_detector_scores"][name]["verdict"]
                    if verdict in ai:
                        counts["ai"] += 1
                    elif verdict in human:
                        counts["human"] += 1
                    elif verdict in neither:
                        counts["uncertain"] += 1
                    else:
                        raise ValueError("unmapped detector verdict %r" % verdict)
                per_det.append({
                    "pipeline_id": pipe, "detector_id": name,
                    "detector_type": dtype, "fidelity_passing_N": n_pass,
                    "human_pct": float(self.fmt_pct(counts["human"], n_pass)),
                    "ai_pct": float(self.fmt_pct(counts["ai"], n_pass)),
                    "uncertain_pct": float(self.fmt_pct(counts["uncertain"], n_pass)),
                    "uncertain_basis": unc_basis,
                    "evidence_artifact_ids": self.evidence_ids(passing)})
        return per_pipe, per_det, unfiltered, raw_by_pipe

    # -- baseline-vs-transformed detection -----------------------------------
    def build_detection(self, variants_by_pipe, originals):
        ai, _human, _neither, _overall = self.buckets()
        det_info = self.detectors()
        table = []
        for pipe in self.pipeline_order():
            variants = variants_by_pipe[pipe]
            passing = [v for v in variants
                       if (v.get("fidelity") or {}).get("fidelity_passing")]
            base_ids = sorted({v["original_id"] for v in variants})
            for name, _key, _dtype in det_info:
                det_v = sum(1 for v in passing
                            if v["per_detector_scores"][name]["verdict"] in ai)
                det_b = sum(1 for sid in base_ids
                            if originals[sid]["per_detector_scores"][name]["verdict"] in ai)
                table.append({
                    "pipeline_id": pipe, "detector_id": name,
                    "baseline_N": len(base_ids),
                    "baseline_detection_rate": round(det_b / len(base_ids), 4),
                    "variant_N": len(passing),
                    "variant_detection_rate": round(det_v / len(passing), 4),
                    "detection_delta": round(det_v / len(passing) -
                                             det_b / len(base_ids), 4)})
        return table

    # -- failure modes + triage ----------------------------------------------
    def wilson(self, k, n, level):
        import math
        if n == 0:
            raise ValueError("wilson with n=0")
        z = self._z_for(level)
        p = k / n
        denom = 1.0 + z * z / n
        center = (p + z * z / (2.0 * n)) / denom
        half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
        return max(0.0, center - half), min(1.0, center + half)

    def _z_for(self, level):
        # Acklam inverse-normal CDF; level comes from config, never literal.
        import math
        p = 1.0 - (1.0 - level) / 2.0
        lo_c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
                -2.549732539343734, 4.374664141464968, 2.938163982698783]
        lo_d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996,
                3.754408661907416]
        if p < 0.5:
            q = math.sqrt(-2.0 * math.log(p))
            num = ((((lo_c[0] * q + lo_c[1]) * q + lo_c[2]) * q + lo_c[3]) * q
                   + lo_c[4]) * q + lo_c[5]
            den = (((lo_d[0] * q + lo_d[1]) * q + lo_d[2]) * q + lo_d[3]) * q + 1.0
            return num / den
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        num = ((((lo_c[0] * q + lo_c[1]) * q + lo_c[2]) * q + lo_c[3]) * q
               + lo_c[4]) * q + lo_c[5]
        den = (((lo_d[0] * q + lo_d[1]) * q + lo_d[2]) * q + lo_d[3]) * q + 1.0
        return -(num / den)

    def severity_bands(self):
        spec = cfg.require_resolved(self.analysis, "failure_severity_definition",
                                    "config/analysis.yaml")
        parts = {}
        for piece in spec.split(";"):
            if "<=" in piece:
                name, val = piece.split("<=")
                parts[name] = float(val)
        return parts["low"], parts["medium"]

    def build_modes(self, variants_by_pipe, originals):
        ai, human, _neither, _overall = self.buckets()
        level = cfg.require_resolved(self.analysis, "analysis_ci_level",
                                     "config/analysis.yaml")
        min_n = cfg.require_resolved(self.analysis, "analysis_minimum_n",
                                     "config/analysis.yaml")
        min_rate = cfg.require_resolved(self.analysis, "analysis_minimum_rate",
                                        "config/analysis.yaml")
        ci_bound = cfg.require_resolved(self.analysis, "analysis_ci_lower_bound",
                                        "config/analysis.yaml")
        low_max, med_max = self.severity_bands()
        order = self.pipeline_order()
        pipe_rank = {p: i for i, p in enumerate(order)}
        det_names = [d[0] for d in self.detectors()]
        det_rank = {d: i for i, d in enumerate(det_names)}
        fail_ids = {}
        for fid, entry in load_json(
                "build/evidence/D4/d3-failure-ids.json").items():
            fail_ids[(entry["detector"], entry["condition"])] = fid
        d4cfg = cfg.load("d4.yaml")
        frozen_run = cfg.require_resolved(d4cfg, "d4_d3a_tables_run_id", "config/d4.yaml")
        for fid, entry in load_json(
                "results/d3a/failure-ids-%s.json" % frozen_run).items():
            fail_ids[(entry["detector"], entry["condition"])] = fid
        cells, significant = [], []
        for pipe in order:
            passing = [v for v in variants_by_pipe[pipe]
                       if (v.get("fidelity") or {}).get("fidelity_passing")]
            n = len(passing)
            for name in det_names:
                flips = 0
                for var in passing:
                    orig = originals[var["original_id"]]["per_detector_scores"][name]
                    entry = var["per_detector_scores"][name]
                    if orig["verdict"] in ai and entry["verdict"] in human:
                        flips += 1
                lo, hi = self.wilson(flips, n, level)
                rate = flips / n
                sig = bool(n >= min_n and rate >= min_rate and lo >= ci_bound)
                if rate <= low_max:
                    sev = "low"
                elif rate <= med_max:
                    sev = "medium"
                else:
                    sev = "high"
                cell = {"pipeline_id": pipe, "detector_id": name, "n": n,
                        "flips": flips, "flip_rate": round(rate, 4),
                        "flip_ci_lo": round(lo, 4), "flip_ci_hi": round(hi, 4),
                        "significant": sig, "severity": sev if sig else None,
                        "failure_id": fail_ids.get((name, pipe))}
                if cell["failure_id"] is None:
                    raise ValueError("no failure ID for %s/%s" % (pipe, name))
                cells.append(cell)
                if sig:
                    significant.append(cell)
        triage = sorted(
            (c for c in cells if c["flips"] > 0),
            key=lambda c: (-c["flips"], pipe_rank[c["pipeline_id"]],
                           det_rank[c["detector_id"]]))
        return cells, significant, triage

    # -- human controls (caveated extra, never section 3C) ---------------------
    def build_human_controls(self, originals):
        ai, human, neither, overall = self.buckets()
        humans = sorted((r for r in originals.values()
                         if r["ground_truth_label"] == "human"),
                        key=lambda r: r["sample_id"])
        if not humans:
            raise ValueError("no scored human originals")
        per_det = []
        for name, _key, dtype in self.detectors():
            counts = {"ai": 0, "human": 0, "uncertain": 0}
            for rec in humans:
                verdict = rec["per_detector_scores"][name]["verdict"]
                if verdict in ai:
                    counts["ai"] += 1
                elif verdict in human:
                    counts["human"] += 1
                elif verdict in neither:
                    counts["uncertain"] += 1
                else:
                    raise ValueError("unmapped detector verdict %r" % verdict)
            n = len(humans)
            per_det.append({
                "detector_id": name, "detector_type": dtype, "human_N": n,
                "human_pct": float(self.fmt_pct(counts["human"], n)),
                "ai_pct": float(self.fmt_pct(counts["ai"], n)),
                "uncertain_pct": float(self.fmt_pct(counts["uncertain"], n))})
        o_counts = {"ai": 0, "human": 0, "uncertain": 0}
        for rec in humans:
            verdict = (rec.get("overall_verbatim") or {})["overall_verdict"]
            for bucket, values in overall.items():
                if verdict in values:
                    o_counts[bucket] += 1
        n = len(humans)
        overall_row = {
            "human_N": n,
            "overall_human_pct": float(self.fmt_pct(o_counts["human"], n)),
            "overall_ai_pct": float(self.fmt_pct(o_counts["ai"], n)),
            "overall_uncertain_pct": float(self.fmt_pct(o_counts["uncertain"], n))}
        return per_det, overall_row

    # -- fixes index summary (INDEX.md is the single source of truth) ---------
    def build_fixes(self):
        path = os.path.join(ROOT, "detector-fixes", "INDEX.md")
        entries = []
        for line in open(path).read().splitlines():
            if not line.startswith("| FIX-"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            (fix_id, targets, failures, conditions, status, fix_type,
             simulation, _evidence, ver_spec) = cells[:9]
            entries.append({
                "fix_id": fix_id,
                "target_detector_ids": [t for t in targets.split(",") if t],
                "failure_ids": [f for f in failures.split(",") if f],
                "condition_ids": [c for c in conditions.split(",") if c],
                "status": status, "fix_type": fix_type,
                "simulation": simulation, "verification_spec": ver_spec})
        if not entries:
            raise ValueError("no entries parsed from INDEX.md")
        return entries

    # -- blocked items (catalog grounds joined to verdict lines) --------------
    def build_blocked(self):
        roster = list(self.d6["d6_blocked_ids"])
        verdicts = {}
        for name in self.d6["d6_blocked_verdicts"]:
            with open(os.path.join(ROOT, "build", name)) as fh:
                verdicts[name] = fh.read().splitlines()
        items = []
        for bid in roster:
            prefix = "d6_%s_" % bid.lower().replace("-", "")
            grounds_raw = cfg.require_resolved(self.d6, prefix + "grounds",
                                               "config/d6.yaml")
            parts = [p.strip() for p in grounds_raw.split("||")]
            if len(parts) % 2:
                raise ValueError("odd grounds parts for " + bid)
            grounds, quoted = [], []
            for fname, substr in zip(parts[0::2], parts[1::2]):
                if fname not in verdicts:
                    raise ValueError("unknown verdict %s for %s" % (fname, bid))
                hits = [ln for ln in verdicts[fname] if substr in ln]
                if not hits:
                    raise ValueError("ground not found for %s: %r" % (bid, substr))
                grounds.append({"verdict": fname, "substring": substr,
                                "matching_lines": len(hits)})
                quoted.append({"verdict": fname, "lines": hits})
            items.append({
                "item_id": bid, "grounds": grounds, "quoted_lines": quoted,
                "reason": cfg.require_resolved(self.d6, prefix + "reason",
                                               "config/d6.yaml"),
                "effect": cfg.require_resolved(self.d6, prefix + "effect",
                                               "config/d6.yaml")})
        return items

    # -- markdown rendering ----------------------------------------------------
    def t_stores(self, number_id, value, notes=""):
        return self.tag(number_id, value, "results/d3+results/d3a+results/d3a-originals",
                        self.recompute_cmd(number_id), ("exact", 0), notes)

    def t_pct(self, number_id, value):
        return self.tag(number_id, value, "results/d3+results/d3a+results/d3a-originals",
                        self.recompute_cmd(number_id), self.pct_tol())

    def t_cfg(self, number_id, value, source):
        return self.tag(number_id, value, source, self.recompute_cmd(number_id),
                        ("exact", 0))

    def t_ev(self, number_id, value, artifact_id):
        return self.tag(number_id, value, artifact_id, self.recompute_cmd(number_id),
                        ("exact", 0))

    def render_head(self, out, ctx):
        out.append("# Final report — defensive detector evaluation")
        out.append("")
        out.append("Generated from frozen artifacts by "
                   "`tools/analysis/d6_report.py`; no claim below is hand-written. "
                   "Every digit-written value carries a trace tag shaped as a "
                   "bracketed value linked to its number id; the tag table lives in "
                   "`build/evidence/D6/traceability.json` and each value is "
                   "recomputed from its cited artifact by "
                   "`tools/analysis/d6_recompute.py`. Section order follows the "
                   "plan: per-pipeline tables in pipeline order, failure modes in "
                   "pipeline order, and a triage list sorted by one stated key.")
        out.append("")
        out.append("## 1. Headline finding")
        out.append("")
        out.append("Across %s detectors, %s pipelines, and %s scored variants, "
                   "the frozen significance bar admits %s significant failure "
                   "modes out of %s detector-by-condition cells. Flips total %s "
                   "and stay diffuse: the largest cell holds %s flips. "
                   "Fidelity medians span %s to %s; the pooled median is %s."
                   % (self.tag("det.count", ctx["det_n"],
                                "build/evidence/D0/frozen/inventory.json",
                                self.recompute_cmd("det.count"), ("exact", 0)),
                      self.t_cfg("cfg.pipes_n", ctx["pipes_n"], "config/pipelines.yaml"),
                      self.t_stores("stores.variants_n", ctx["variants_n"]),
                      self.t_stores("modes.sig_n", ctx["sig_n"]),
                      self.t_stores("modes.cells_n", ctx["cells_n"]),
                      self.t_stores("modes.flips_total", ctx["flips_total"]),
                      self.t_stores("modes.max_flips", ctx["max_flips"]),
                      self.t_stores("dist.median_min", ctx["median_min"]),
                      self.t_stores("dist.median_max", ctx["median_max"]),
                      self.t_stores("dist.overall_median", ctx["overall_median"])))
        out.append("")
        out.append("Frozen bars applied throughout: fidelity threshold %s, "
                   "LOW-N floor %s, significance floor N %s with rate %s and "
                   "interval lower bound %s at level %s, severity breaks at %s "
                   "and %s, human-FPR ceiling %s. Dataset: %s samples (%s AI, "
                   "%s human), bands S %s to %s words, M %s to %s, L %s to %s. "
                   "Measurement metrology holds %s scored probe records outside "
                   "the variant set."
                   % (self.t_cfg("cfg.threshold", ctx["threshold"], "config/fidelity.yaml"),
                      self.t_cfg("cfg.low_n", ctx["low_n"], "config/reporting.yaml"),
                      self.t_cfg("cfg.min_n", ctx["min_n"], "config/analysis.yaml"),
                      self.t_cfg("cfg.min_rate", ctx["min_rate"], "config/analysis.yaml"),
                      self.t_cfg("cfg.ci_bound", ctx["ci_bound"], "config/analysis.yaml"),
                      self.t_cfg("cfg.ci_level", ctx["ci_level"], "config/analysis.yaml"),
                      self.t_cfg("cfg.sev_low", ctx["sev_low"], "config/analysis.yaml"),
                      self.t_cfg("cfg.sev_med", ctx["sev_med"], "config/analysis.yaml"),
                      self.t_cfg("cfg.fpr_bound", ctx["fpr_bound"], "config/analysis.yaml"),
                      self.tag("manifest.v1_samples", ctx["v1_n"],
                                     "datasets/v1/manifest.json",
                                     self.recompute_cmd("manifest.v1_samples"),
                                     ("exact", 0)),
                      self.tag("manifest.v1_ai", ctx["v1_ai"],
                                     "datasets/v1/manifest.json",
                                     self.recompute_cmd("manifest.v1_ai"),
                                     ("exact", 0)),
                      self.tag("manifest.v1_human", ctx["v1_human"],
                                     "datasets/v1/manifest.json",
                                     self.recompute_cmd("manifest.v1_human"),
                                     ("exact", 0)),
                      self.t_cfg("cfg.band_s_min", ctx["band_s_min"], "config/datasets.yaml"),
                      self.t_cfg("cfg.band_s_max", ctx["band_s_max"], "config/datasets.yaml"),
                      self.t_cfg("cfg.band_m_min", ctx["band_m_min"], "config/datasets.yaml"),
                      self.t_cfg("cfg.band_m_max", ctx["band_m_max"], "config/datasets.yaml"),
                      self.t_cfg("cfg.band_l_min", ctx["band_l_min"], "config/datasets.yaml"),
                      self.t_cfg("cfg.band_l_max", ctx["band_l_max"], "config/datasets.yaml"),
                      self.t_stores("stores.d2_n", ctx["d2_n"])))
        out.append("")

    def render_s3c(self, out, per_pipe):
        out.append("## 2. Per-pipeline results (section 3C table)")
        out.append("")
        out.append("Rows follow pipeline order, never a rate ranking. Percentages "
                   "use fidelity-passing variants only; overall shares bucket the "
                   "provider verdict verbatim. Spot-check fields stay null: rating "
                   "never ran (see blocked item B-003).")
        out.append("")
        out.append("| pipeline | config hash | steps | total N | passing N | "
                   "passing rate | human pct | AI pct | uncertain pct | overall basis | "
                   "fidelity median | spread | spot rate | spot N | LOW-N | evidence |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
                   "--- | --- | --- | --- | --- | --- |")
        for row in per_pipe:
            pipe = row["pipeline_id"]
            steps = " + ".join("%s@%s" % (s["name"], s["version"]) for s in row["steps"])
            out.append("| %s | `%s` | `%s` | %s | %s | %s | %s | %s | %s | %s | "
                       "%s | %s | null | %s | %s | %s artifacts |"
                       % (pipe, row["config_hash"], steps,
                          self.t_stores("s3c.%s.total_n" % pipe, row["total_samples_N"]),
                          self.t_stores("s3c.%s.passing_n" % pipe,
                                        row["fidelity_passing_N"]),
                          self.t_stores("s3c.%s.passing_rate" % pipe,
                                        row["fidelity_passing_rate"]),
                          self.t_pct("s3c.%s.overall_human_pct" % pipe,
                                     row["overall_human_pct"]),
                          self.t_pct("s3c.%s.overall_ai_pct" % pipe, row["overall_ai_pct"]),
                          self.t_pct("s3c.%s.overall_uncertain_pct" % pipe,
                                     row["overall_uncertain_pct"]),
                          row["overall_basis"],
                          self.t_stores("s3c.%s.fidelity_median" % pipe,
                                        row["fidelity_median"]),
                          self.t_stores("s3c.%s.fidelity_spread" % pipe,
                                        row["fidelity_spread"]),
                          self.t_stores("s3c.%s.spot_n" % pipe, row["spot_check_N"]),
                          self.t_stores("s3c.%s.low_n" % pipe,
                                        "true" if row["low_N_flag"] else "false"),
                          self.t_stores("s3c.%s.evidence_n" % pipe,
                                        len(row["evidence_artifact_ids"]))))
        out.append("")

    def render_detail(self, out, per_det, det_keys):
        out.append("## 3. Per-detector detail (section 3C detail table)")
        out.append("")
        out.append("One row per pipeline and detector in pipeline order, then "
                   "inventory order. Uncertain/other counts the intermediate "
                   "verdict band, recorded once per row.")
        out.append("")
        out.append("| pipeline | detector | type | passing N | human pct | AI pct | "
                   "uncertain pct | uncertain basis | evidence |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in per_det:
            pipe = row["pipeline_id"]
            key = det_keys[row["detector_id"]]
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s artifacts |"
                       % (pipe, row["detector_id"], row["detector_type"],
                          self.t_stores("det.%s.%s.n" % (pipe, key),
                                        row["fidelity_passing_N"]),
                          self.t_pct("det.%s.%s.human_pct" % (pipe, key), row["human_pct"]),
                          self.t_pct("det.%s.%s.ai_pct" % (pipe, key), row["ai_pct"]),
                          self.t_pct("det.%s.%s.uncertain_pct" % (pipe, key),
                                     row["uncertain_pct"]),
                          row["uncertain_basis"],
                          self.t_stores("det.%s.%s.evidence_n" % (pipe, key),
                                        len(row["evidence_artifact_ids"]))))
        out.append("")

    def render_unfiltered(self, out, unfiltered):
        out.append("## 4. Unfiltered view (section 3C unfiltered table)")
        out.append("")
        out.append("Same pipelines over all variants, kept in this separate table "
                   "so degraded text can never inflate a passing rate.")
        out.append("")
        out.append("| pipeline | total N | passing N | passing rate | human pct | "
                   "AI pct | uncertain pct | fidelity median | spread | spot N | "
                   "LOW-N | evidence |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
                   "--- | --- |")
        for row in unfiltered:
            pipe = row["pipeline_id"]
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s artifacts |"
                       % (pipe,
                          self.t_stores("unf.%s.total_n" % pipe,
                                        row["total_samples_N_unfiltered"]),
                          self.t_stores("s3c.%s.passing_n" % pipe,
                                        row["fidelity_passing_N_unfiltered"]),
                          self.t_stores("s3c.%s.passing_rate" % pipe,
                                        row["fidelity_passing_rate_unfiltered"]),
                          self.t_pct("unf.%s.overall_human_pct" % pipe,
                                     row["overall_human_pct_unfiltered"]),
                          self.t_pct("unf.%s.overall_ai_pct" % pipe,
                                     row["overall_ai_pct_unfiltered"]),
                          self.t_pct("unf.%s.overall_uncertain_pct" % pipe,
                                     row["overall_uncertain_pct_unfiltered"]),
                          self.t_stores("unf.%s.fidelity_median" % pipe,
                                        row["fidelity_median_unfiltered"]),
                          self.t_stores("unf.%s.fidelity_spread" % pipe,
                                        row["fidelity_spread_unfiltered"]),
                          self.t_stores("unf.%s.spot_n" % pipe,
                                        row["spot_check_N_unfiltered"]),
                          self.t_stores("unf.%s.low_n" % pipe, "true" if
                                        row["low_N_flag_unfiltered"] else "false"),
                          self.t_stores("unf.%s.evidence_n" % pipe, len(
                              row["evidence_artifact_ids_unfiltered"]))))
        out.append("")

    def render_detection(self, out, detection, det_keys):
        out.append("## 5. Baseline versus transformed detection")
        out.append("")
        out.append("Per-detector AI-verdict share on originals beside the share on "
                   "fidelity-passing variants, with the delta. Baselines are the "
                   "AI originals behind each pipeline; human controls sit in "
                   "their own section.")
        out.append("")
        out.append("| pipeline | detector | baseline N | baseline rate | variant N | "
                   "variant rate | delta |")
        out.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in detection:
            pipe = row["pipeline_id"]
            key = det_keys[row["detector_id"]]
            out.append("| %s | %s | %s | %s | %s | %s | %s |"
                       % (pipe, row["detector_id"],
                          self.t_stores("detect.%s.baseline_n" % pipe,
                                        row["baseline_N"]),
                          self.t_stores("detect.%s.%s.baseline_rate" % (pipe, key),
                                        row["baseline_detection_rate"]),
                          self.t_stores("s3c.%s.passing_n" % pipe, row["variant_N"]),
                          self.t_stores("detect.%s.%s.variant_rate" % (pipe, key),
                                        row["variant_detection_rate"]),
                          self.t_stores("detect.%s.%s.delta" % (pipe, key),
                                        row["detection_delta"])))
        out.append("")

    def render_fidelity(self, out, per_pipe, variants_by_pipe, ctx):
        out.append("## 6. Fidelity distribution")
        out.append("")
        out.append("Cosine to the original per pipeline, then the pooled row. "
                   "The gate threshold is the frozen value from the headline; "
                   "variants below it are degraded text, not detector failures.")
        out.append("")
        out.append("| pipeline | N | median | min | max | spread |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for row in per_pipe:
            pipe = row["pipeline_id"]
            passing = [v for v in variants_by_pipe[pipe]
                       if (v.get("fidelity") or {}).get("fidelity_passing")]
            cos = sorted(v["fidelity"]["cosine"] for v in passing)
            out.append("| %s | %s | %s | %s | %s | %s |"
                       % (pipe,
                          self.t_stores("s3c.%s.passing_n" % pipe, len(passing)),
                          self.t_stores("s3c.%s.fidelity_median" % pipe,
                                        row["fidelity_median"]),
                          self.t_stores("dist.%s.min" % pipe, round(min(cos), 4)),
                          self.t_stores("dist.%s.max" % pipe, round(max(cos), 4)),
                          self.t_stores("s3c.%s.fidelity_spread" % pipe,
                                        row["fidelity_spread"])))
        out.append("| pooled | %s | %s | %s | %s | %s |"
                   % (self.t_stores("dist.pooled_n", ctx["pooled_n"]),
                      self.t_stores("dist.overall_median", ctx["overall_median"]),
                      self.t_stores("dist.overall_min", ctx["overall_min"]),
                      self.t_stores("dist.overall_max", ctx["overall_max"]),
                      self.t_stores("dist.overall_spread", ctx["overall_spread"])))
        out.append("")

    def render_mapping(self, out, raw_by_pipe):
        out.append("## 7. Overall-verdict mapping audit")
        out.append("")
        out.append("Raw provider verdict counts behind the bucketed overall shares, "
                   "so a reader can re-bucket. Buckets: AI holds the two "
                   "AI-denoting verdicts; human holds the clean verdict and the "
                   "low-risk verdict; uncertain holds the suspicious verdict.")
        out.append("")
        out.append("| pipeline | Likely AI-generated | Slop detected | Low risk | "
                   "Clean human-written | Suspicious |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        keys = [("Likely AI-generated", "likely_ai"), ("Slop detected", "slop_detected"),
                ("Low risk", "low_risk"), ("Clean — likely human-written", "clean_human"),
                ("Suspicious", "suspicious")]
        for pipe in self.pipeline_order():
            counts = raw_by_pipe[pipe]
            cells = [self.t_stores("oc.%s.%s" % (pipe, short), counts.get(raw, 0))
                     for raw, short in keys]
            out.append("| %s | %s |" % (pipe, " | ".join(cells)))
        out.append("")

    def render_human(self, out, per_det, overall_row):
        out.append("## 8. Human controls (caveated, not section 3C)")
        out.append("")
        out.append("Detector behavior on the scored human originals. These controls "
                   "are craft-briefed prose from the same model family as the AI "
                   "arm, not wild writing (blocked item B-006 carries the caveat); "
                   "read every rate below as conditional on that fact.")
        out.append("")
        out.append("| detector | type | human N | human pct | AI pct | uncertain pct |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        det_keys = {d[0]: d[1] for d in self.detectors()}
        for row in per_det:
            key = det_keys[row["detector_id"]]
            out.append("| %s | %s | %s | %s | %s | %s |"
                       % (row["detector_id"], row["detector_type"],
                          self.t_stores("hum.n", row["human_N"]),
                          self.t_pct("hum.%s.human_pct" % key, row["human_pct"]),
                          self.t_pct("hum.%s.ai_pct" % key, row["ai_pct"]),
                          self.t_pct("hum.%s.uncertain_pct" % key, row["uncertain_pct"])))
        out.append("")
        out.append("Overall on human controls: human %s, AI %s, uncertain %s "
                   "(N %s)."
                   % (self.t_pct("hum.overall_human_pct", overall_row["overall_human_pct"]),
                      self.t_pct("hum.overall_ai_pct", overall_row["overall_ai_pct"]),
                      self.t_pct("hum.overall_uncertain_pct",
                                 overall_row["overall_uncertain_pct"]),
                      self.t_stores("hum.n", overall_row["human_N"])))
        out.append("")

    def render_modes(self, out, sig_by_pipe, fixes):
        out.append("## 9. Failure modes and fix linkage")
        out.append("")
        out.append("Significant modes in pipeline order, each with its fix link. "
                   "The bar admits no mode, so the table records zeros honestly "
                   "instead of omitting the section; condition-level entries from "
                   "the advanced datasets still link below.")
        out.append("")
        out.append("| pipeline | significant modes | fix link | severity |")
        out.append("| --- | --- | --- | --- |")
        fix_by_cond = {}
        for entry in fixes:
            for cond in entry["condition_ids"]:
                fix_by_cond[cond] = entry["fix_id"]
        for pipe in self.pipeline_order():
            link = "`%s`" % fix_by_cond[pipe] if pipe in fix_by_cond else "none"
            out.append("| %s | %s | %s | null |"
                       % (pipe, self.t_stores("sig.%s.n" % pipe, sig_by_pipe[pipe]), link))
        out.append("")

    def render_triage(self, out, triage):
        out.append("## 10. Triage list (sub-threshold watch)")
        out.append("")
        out.append("Cells with at least one flip, sorted by "
                   "fidelity-passing flip count descending, ties by pipeline "
                   "order then inventory order. Triage order is not a "
                   "recommendation and not a pipeline ranking.")
        out.append("")
        out.append("| rank | pipeline | detector | flips | N | rate | CI lo | CI hi | "
                   "failure ID |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for i, cell in enumerate(triage, 1):
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s | `%s` |"
                       % (self.t_stores("triage.%d.rank" % i, i),
                          cell["pipeline_id"], cell["detector_id"],
                          self.t_stores("triage.%d.flips" % i, cell["flips"]),
                          self.t_stores("triage.%d.n" % i, cell["n"]),
                          self.t_stores("triage.%d.rate" % i, cell["flip_rate"]),
                          self.t_stores("triage.%d.ci_lo" % i, cell["flip_ci_lo"]),
                          self.t_stores("triage.%d.ci_hi" % i, cell["flip_ci_hi"]),
                          cell["failure_id"]))
        out.append("")

    def render_fixes(self, out, fixes):
        out.append("## 11. Fixes index summary")
        out.append("")
        out.append("The hardening handoff holds %s entries, all condition-level, "
                   "all carrying status awaiting review and application in a "
                   "future phase. No entry claims a detector is fixed."
                   % self.t_cfg("fixes.n", len(fixes), "detector-fixes/INDEX.md"))
        out.append("")
        out.append("| fix | conditions | detectors covered | failure IDs | type | "
                   "simulation | status | verification spec |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for entry in fixes:
            short = entry["fix_id"].lower().replace("-", "")
            out.append("| `%s` | %s | %s | %s | %s | %s | `%s` | `%s` |"
                       % (entry["fix_id"], ", ".join(entry["condition_ids"]),
                          self.t_cfg("fixes.%s.detectors_n" % short,
                                     len(entry["target_detector_ids"]),
                                     "detector-fixes/INDEX.md"),
                          self.t_cfg("fixes.%s.failures_n" % short,
                                     len(entry["failure_ids"]), "detector-fixes/INDEX.md"),
                          entry["fix_type"], entry["simulation"], entry["status"],
                          entry["verification_spec"]))
        out.append("")

    def render_regression(self, out, ctx):
        out.append("## 12. Regression and reproducibility")
        out.append("")
        drift = load_json("build/evidence/D5/drift-report.json")
        stats = drift["regen"]["stats"]
        clean = load_json("build/evidence/D5/cleanroom-diff.json")["scores"]
        gate = drift["gate"]
        impl_run = cfg.require_resolved(self.d6, "d6_d5_impl_run_id", "config/d6.yaml")
        scan_rel = "build/evidence/D5/runs/%s/scan-report.json" % impl_run
        scan = load_json(scan_rel)
        out.append("Stored variants rescored through a fresh pinned container: %s "
                   "variants, verdict %s. Fresh-call regeneration drift over %s "
                   "samples: fidelity mean %s with minimum %s, score delta mean "
                   "%s with maximum %s. Cleanroom re-runs compared %s scores "
                   "with %s mismatches and worst delta %s; the analysis report "
                   "reproduced %s and %s dataset manifests matched except for "
                   "their run IDs while %s fix files differed. The exposure gate "
                   "found zero forbidden hits over %s allowlist IDs, %s inventoried "
                   "batch runners, and %s reviewed docs."
                   % (self.t_stores("reg.variants_rescored_n", ctx["variants_n"]),
                      self.t_ev("reg.rescoring_pass",
                                "true" if drift["rescoring"]["pass"] else "false",
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.drift_n", stats["n"],
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.drift_fid_mean", round(stats["fidelity_mean"], 4),
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.drift_fid_min", stats["fidelity_min"],
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.drift_delta_mean", round(stats["delta_mean"], 4),
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.drift_delta_max", stats["delta_max"],
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.cleanroom_compared_n", clean["compared"],
                                "build/evidence/D5/cleanroom-diff.json"),
                      self.t_ev("reg.cleanroom_mismatches_n", len(clean["mismatches"]),
                                "build/evidence/D5/cleanroom-diff.json"),
                      self.t_ev("reg.cleanroom_worst_d", clean["worst_delta"],
                                "build/evidence/D5/cleanroom-diff.json"),
                      self.t_ev("reg.d4_identical",
                                "true" if drift["cleanroom"]["d4_report_identical"] else "false",
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.manifests_identical_n",
                                sum(1 for m in drift["cleanroom"]["manifests_identical"].values()
                                    if m["identical_except_run_id"]),
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.fixes_differing_n",
                                len(drift["cleanroom"]["fixes_tree"]["differing"]),
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.allowlist_n", gate["allowlist_ids"],
                                "build/evidence/D5/drift-report.json"),
                      self.t_ev("reg.clis_n", len(scan["findings"]["cli_inventory"]),
                                scan_rel),
                      self.t_ev("reg.docs_n", len(scan["scanned_docs"]),
                                scan_rel)))
        out.append("")

    def render_blocked(self, out, items):
        out.append("## 13. Blocked items")
        out.append("")
        out.append("Every blocked or never-run item carried forward from the "
                   "milestone verdicts, with its reason and its effect on "
                   "conclusions. No conclusion in the next section depends on a "
                   "blocked item without saying so.")
        out.append("")
        out.append("| item | verdicts | reason | effect |")
        out.append("| --- | --- | --- | --- |")
        for item in items:
            verdicts = ", ".join(sorted({g["verdict"] for g in item["grounds"]}))
            out.append("| %s | %s | %s | %s |"
                       % (item["item_id"], verdicts, item["reason"], item["effect"]))
        out.append("")
        out.append("Verdict excerpts behind the table:")
        out.append("")
        for item in items:
            out.append("`%s`" % item["item_id"])
            out.append("")
            for quote in item["quoted_lines"]:
                for line in quote["lines"]:
                    out.append("> %s" % line.strip())
            out.append("")

    def render_conclusions(self, out, ctx):
        out.append("## 14. Limitations and conclusions")
        out.append("")
        out.append("B-001: overall shares are verbatim buckets of provider "
                   "verdicts; the campaign never estimates a combination rule, "
                   "so claims about cross-detector aggregation are absent by "
                   "design. B-002: transport-fault behavior appears only as the "
                   "D2 proof that failures block loudly with no score recorded. "
                   "B-003: fidelity-passing means passing the automated gate; "
                   "every detector-failure conclusion below is conditional on "
                   "automated fidelity, and promoting passing variants to "
                   "meaning-preserved awaits the external rating protocol. "
                   "B-004: nothing here describes REST behavior; all variants "
                   "were generated and scored locally. B-005: the per-pipeline "
                   "tables resolve the section 3C half of the D5 scope note in "
                   "this report, while the section 3B REST half stays uncovered "
                   "and unclaimed. B-006: human-side rates describe "
                   "craft-briefed prose; no wild-writing generalization is made.")
        out.append("")
        out.append("Conclusions, within those bounds: no detector-by-condition "
                   "group fails significantly under the frozen bar (%s of %s "
                   "cells); flips stay diffuse at %s with a cell maximum of %s; "
                   "fidelity holds across intensities with pooled median %s; "
                   "rescoring reproduces every stored variant exactly and the "
                   "cleanroom reproduces every compared score. The handoff is "
                   "this report plus the fixes folder, all proposals unapplied."
                   % (self.t_stores("modes.sig_n", ctx["sig_n"]),
                      self.t_stores("modes.cells_n", ctx["cells_n"]),
                      self.t_stores("modes.flips_total", ctx["flips_total"]),
                      self.t_stores("modes.max_flips", ctx["max_flips"]),
                      self.t_stores("dist.overall_median", ctx["overall_median"])))
        out.append("")

    def render_scope(self, out):
        out.append("## 15. Scope limits restated")
        out.append("")
        out.append("Applying fixes, retraining any model, changing any "
                   "production threshold, and any user-facing tool remain future "
                   "work by design. No detector was edited: the Docker "
                   "deployment stayed read-only throughout, and the fixes folder "
                   "holds proposals only. No masking tool was built, tuned, "
                   "shipped, or deployed; the exposure gate proves the negative "
                   "in every regression run. Human-side rates carry the "
                   "craft-briefed caveat from B-006 wherever they appear.")
        out.append("")

    def render_apply(self, out):
        out.append("## 16. Future apply phase")
        out.append("")
        out.append("Applying a fix would require edit permission for the Docker "
                   "deployment first. Each entry would then be applied singly, "
                   "followed by a re-run of the measurement suites and a "
                   "post-fix detection measurement against the frozen baseline "
                   "in this report. No entry counts as applied until its "
                   "verification spec passes on the modified detector, with "
                   "retraining data drawn from the entry data spec and the "
                   "held-out verification set kept disjoint from augmentation "
                   "data. Threshold moves would re-check the human-FPR ceiling; "
                   "rollback triggers sit in each entry.")
        out.append("")

    def render_release(self, out):
        out.append("## 17. Release checklist")
        out.append("")
        out.append("The suite runs %s release items: `no-secrets-in-diff`, "
                   "`no-debug-endpoints`, `no-detector-edits`, and "
                   "`no-humanizer-artifact`. The detector item re-executes the "
                   "Docker no-edit proof and the artifact item re-executes the "
                   "exposure gate; the result of all four lives in the run "
                   "record beside this report."
                   % self.t_cfg("cfg.release_n", len(self.d6["d6_release_items"]),
                                "config/d6.yaml"))
        out.append("")

    def render_trace_note(self, out):
        out.append("## 18. Traceability note")
        out.append("")
        total = len(self.numbers) + 1
        out.append("This report carries %s traced values. Each tag names its "
                   "artifact and the exact recomputation command; rerunning any "
                   "command from the repository root reproduces the tagged "
                   "value. Quote lines hold verbatim verdict excerpts and code "
                   "spans hold identifiers; neither carries report values."
                   % self.tag("meta.numbers_n", total,
                                  "build/evidence/D6/traceability.json",
                                  self.recompute_cmd("meta.numbers_n"),
                                  ("exact", 0),
                                  "count of traceability rows, self-counted"))
        out.append("")

    # -- driver --------------------------------------------------------------
    def build_all(self):
        d3, d3a, originals, d2recs = self.load_all()
        variants_by_pipe = {}
        for rec in d3 + d3a:
            variants_by_pipe.setdefault(rec["condition_id"], []).append(rec)
        per_pipe, per_det, unfiltered, raw_by_pipe = self.build_tables(
            variants_by_pipe, originals)
        detection = self.build_detection(variants_by_pipe, originals)
        _cells, significant, triage = self.build_modes(variants_by_pipe, originals)
        hum_det, hum_overall = self.build_human_controls(originals)
        fixes = self.build_fixes()
        blocked = self.build_blocked()
        pooled = sorted(v["fidelity"]["cosine"] for v in d3 + d3a
                        if (v.get("fidelity") or {}).get("fidelity_passing"))
        medians = [r["fidelity_median"] for r in per_pipe]
        manifest = load_json("datasets/v1/manifest.json")
        labels = [s["ground_truth_label"] for s in manifest["samples"]]
        datasets = cfg.load("datasets.yaml")
        fidelity = cfg.load("fidelity.yaml")
        low_max, med_max = self.severity_bands()
        sig_by_pipe = {p: 0 for p in self.pipeline_order()}
        for cell in significant:
            sig_by_pipe[cell["pipeline_id"]] += 1
        ctx = {
            "det_n": len(self.detectors()),
            "pipes_n": len(self.pipeline_order()),
            "variants_n": len(d3) + len(d3a),
            "d2_n": len(d2recs),
            "sig_n": len(significant), "cells_n": len(_cells),
            "flips_total": sum(c["flips"] for c in _cells),
            "max_flips": max(c["flips"] for c in _cells),
            "median_min": min(medians), "median_max": max(medians),
            "overall_median": round(statistics.median(pooled), 4),
            "overall_min": round(min(pooled), 4),
            "overall_max": round(max(pooled), 4),
            "overall_spread": round(max(pooled) - min(pooled), 4),
            "pooled_n": len(pooled),
            "threshold": cfg.require_resolved(fidelity, "fidelity_threshold",
                                              "config/fidelity.yaml"),
            "low_n": cfg.require_resolved(self.reporting, "reporting_low_n_minimum",
                                           "config/reporting.yaml"),
            "min_n": cfg.require_resolved(self.analysis, "analysis_minimum_n",
                                           "config/analysis.yaml"),
            "min_rate": cfg.require_resolved(self.analysis, "analysis_minimum_rate",
                                             "config/analysis.yaml"),
            "ci_bound": cfg.require_resolved(self.analysis, "analysis_ci_lower_bound",
                                             "config/analysis.yaml"),
            "ci_level": cfg.require_resolved(self.analysis, "analysis_ci_level",
                                             "config/analysis.yaml"),
            "sev_low": low_max, "sev_med": med_max,
            "fpr_bound": cfg.require_resolved(self.analysis, "analysis_human_fpr_bound",
                                              "config/analysis.yaml"),
            "v1_n": len(labels), "v1_ai": sum(1 for l in labels if l == "ai"),
            "v1_human": sum(1 for l in labels if l == "human"),
            "band_s_min": datasets["band_S_min_words"],
            "band_s_max": datasets["band_S_max_words"],
            "band_m_min": datasets["band_M_min_words"],
            "band_m_max": datasets["band_M_max_words"],
            "band_l_min": datasets["band_L_min_words"],
            "band_l_max": datasets["band_L_max_words"],
        }
        det_keys = {d[0]: d[1] for d in self.detectors()}
        out = []
        self.render_head(out, ctx)
        self.render_s3c(out, per_pipe)
        self.render_detail(out, per_det, det_keys)
        self.render_unfiltered(out, unfiltered)
        self.render_detection(out, detection, det_keys)
        self.render_fidelity(out, per_pipe, variants_by_pipe, ctx)
        self.render_mapping(out, raw_by_pipe)
        self.render_human(out, hum_det, hum_overall)
        self.render_modes(out, sig_by_pipe, fixes)
        self.render_triage(out, triage)
        self.render_fixes(out, fixes)
        self.render_regression(out, ctx)
        self.render_blocked(out, blocked)
        self.render_conclusions(out, ctx)
        self.render_scope(out)
        self.render_apply(out)
        self.render_release(out)
        self.render_trace_note(out)
        tables = {
            "schema": "s3c-v1-plus-d6",
            "pipeline_order": self.pipeline_order(),
            "per_pipeline": per_pipe,
            "per_detector": per_det,
            "unfiltered": unfiltered,
            "detection": detection,
            "triage": triage,
            "human_controls": hum_det,
            "human_overall": hum_overall,
            "fixes": fixes,
            "modes_summary": {"cells_n": ctx["cells_n"], "sig_n": ctx["sig_n"],
                              "flips_total": ctx["flips_total"],
                              "max_flips": ctx["max_flips"]},
        }
        return out, tables, blocked


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    rep = Report()
    lines, tables, blocked = rep.build_all()
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "final-tables.json"), "w") as fh:
        json.dump(tables, fh, indent=2, sort_keys=True)
    with open(os.path.join(args.out, "traceability.json"), "w") as fh:
        json.dump({"numbers": rep.numbers}, fh, indent=2, sort_keys=True)
    with open(os.path.join(args.out, "blocked-items.json"), "w") as fh:
        json.dump({"items": blocked}, fh, indent=2, sort_keys=True)
    with open(args.report, "w") as fh:
        fh.write("\n".join(lines))
    print("report: %d lines, %d tables rows, %d traced numbers, %d blocked items"
          % (len(lines), len(tables["per_detector"]) + len(tables["per_pipeline"]),
             len(rep.numbers), len(blocked)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
