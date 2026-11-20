"""D6 independent recomputation — one command per traced number.

Recomputes every report value from its primary artifact with code written
independently from the generator (separate Wilson, separate loops, separate
bucketing over the same frozen configs). Prints the recomputed value only.
Unknown number IDs fail loudly (exit 2), never print a default.
Usage: d6_recompute.py <number_id>   (run from the repository root)
"""
import glob
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)


def read_json(rel):
    with open(os.path.join(ROOT, rel)) as fh:
        return json.load(fh)


def read_records(store):
    paths = sorted(glob.glob(os.path.join(ROOT, store, "records", "*.json")))
    if not paths:
        raise ValueError("no records in " + store)
    return [read_json(os.path.relpath(p, ROOT)) for p in paths]


def inv_z(level):
    # Inverse-normal CDF via the three-region Acklam form (own derivation).
    want = 1.0 - (1.0 - level) / 2.0
    a_hi = [-39.69683028665376, 220.9460984245205, -275.9285104469687,
            138.3577518672690, -30.66479806614716, 2.506628277459239]
    b_hi = [-54.47609879822406, 161.585836580409, -155.6989798598866,
            66.80131188771972, -13.28068155288572]
    c_lo = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
            -2.549732539343734, 4.374664141464968, 2.938163982698783]
    d_lo = [0.007784695709041462, 0.3224671290700398, 2.445134137142996,
            3.754408661907416]

    def tail(qq, upper):
        top = ((((c_lo[0] * qq + c_lo[1]) * qq + c_lo[2]) * qq + c_lo[3]) * qq
               + c_lo[4]) * qq + c_lo[5]
        bot = ((((d_lo[0] * qq + d_lo[1]) * qq + d_lo[2]) * qq + d_lo[3]) * qq
               + 1.0)
        return -(top / bot) if upper else top / bot

    if want < 0.02425:
        return tail(math.sqrt(-2.0 * math.log(want)), False)
    if want <= 0.97575:
        q, r = want - 0.5, (want - 0.5) ** 2
        top = (((((a_hi[0] * r + a_hi[1]) * r + a_hi[2]) * r + a_hi[3]) * r
                + a_hi[4]) * r + a_hi[5]) * q
        bot = ((((b_hi[0] * r + b_hi[1]) * r + b_hi[2]) * r + b_hi[3]) * r
               + b_hi[4]) * r + 1.0
        return top / bot
    return tail(math.sqrt(-2.0 * math.log(1.0 - want)), True)


def wilson_interval(hits, trials, level):
    zed = inv_z(level)
    frac = hits / trials
    den = 1.0 + zed * zed / trials
    mid = (frac + zed * zed / (2.0 * trials)) / den
    rad = zed * math.sqrt(frac * (1.0 - frac) / trials
                          + zed * zed / (4.0 * trials * trials)) / den
    return max(0.0, mid - rad), min(1.0, mid + rad)


class World(object):
    def __init__(self):
        self.d6 = cfg.load("d6.yaml")
        self.analysis = cfg.load("analysis.yaml")
        self.pipes = cfg.load("pipelines.yaml")
        self.reporting = cfg.load("reporting.yaml")
        self.fidelity = cfg.load("fidelity.yaml")
        self.datasets = cfg.load("datasets.yaml")
        self.tols = cfg.load("tolerances.yaml")
        self.pct_dec = cfg.require_resolved(self.d6, "d6_pct_decimals", "config/d6.yaml")
        self.frac_dec = cfg.require_resolved(self.d6, "d6_frac_decimals", "config/d6.yaml")
        self.ai = set(self.analysis["flip_verdict_map_ai"])
        self.human = set(self.analysis["flip_verdict_map_human"])
        self.neither = set(self.analysis["flip_verdict_map_neither"])
        self.overall = {
            "ai": set(self.d6["d6_overall_bucket_ai"]),
            "human": set(self.d6["d6_overall_bucket_human"]),
            "uncertain": set(self.d6["d6_overall_bucket_uncertain"])}
        inv = read_json("build/evidence/D0/frozen/inventory.json")["payload"]["detectors"]
        self.detectors = [(d["name"], d["key"]) for d in inv]
        self.det_by_key = {d["key"]: d["name"] for d in inv}
        self.order = list(self.pipes["dataset_pipelines"]) + list(self.pipes["d3a_pipelines"])
        self.d3 = read_records("results/d3")
        self.d3a = read_records("results/d3a")
        self.d2 = read_records("results/d2")
        self.originals = {}
        for rec in read_records("results/d3a-originals"):
            self.originals[rec["sample_id"]] = rec
        self.grouped = {}
        for rec in self.d3 + self.d3a:
            self.grouped.setdefault(rec["condition_id"], []).append(rec)

    def passing(self, pipe):
        return [v for v in self.grouped[pipe]
                if (v.get("fidelity") or {}).get("fidelity_passing")]

    def pct(self, part, whole):
        if not whole:
            return "0.0"
        return "%.*f" % (self.pct_dec, 100.0 * part / whole)

    def frac(self, value):
        return str(round(value, self.frac_dec))

    def boolean(self, value):
        return "true" if value else "false"

    def overall_bucket(self, verdict):
        for bucket, values in self.overall.items():
            if verdict in values:
                return bucket
        raise ValueError("unmapped overall verdict %r" % verdict)

    def detector_bucket(self, verdict):
        if verdict in self.ai:
            return "ai"
        if verdict in self.human:
            return "human"
        if verdict in self.neither:
            return "uncertain"
        raise ValueError("unmapped detector verdict %r" % verdict)

    def severity_pair(self):
        spec = cfg.require_resolved(self.analysis, "failure_severity_definition",
                                    "config/analysis.yaml")
        out = {}
        for chunk in spec.split(";"):
            if "<=" in chunk:
                name, val = chunk.split("<=")
                out[name] = float(val)
        return out["low"], out["medium"]

    def index_entries(self):
        path = os.path.join(ROOT, "detector-fixes", "INDEX.md")
        entries = []
        for line in open(path).read().splitlines():
            if not line.startswith("| FIX-"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            entries.append({
                "fix_id": cells[0],
                "targets": [t for t in cells[1].split(",") if t],
                "failures": [f for f in cells[2].split(",") if f],
                "conditions": [c for c in cells[3].split(",") if c],
                "status": cells[4]})
        if not entries:
            raise ValueError("no INDEX.md entries")
        return entries

    def cell_stats(self):
        level = cfg.require_resolved(self.analysis, "analysis_ci_level",
                                     "config/analysis.yaml")
        min_n = cfg.require_resolved(self.analysis, "analysis_minimum_n",
                                     "config/analysis.yaml")
        min_rate = cfg.require_resolved(self.analysis, "analysis_minimum_rate",
                                        "config/analysis.yaml")
        ci_bound = cfg.require_resolved(self.analysis, "analysis_ci_lower_bound",
                                        "config/analysis.yaml")
        cells = []
        for pipe in self.order:
            ok = self.passing(pipe)
            count = len(ok)
            for name, _key in self.detectors:
                flips = 0
                for var in ok:
                    before = self.originals[var["original_id"]][
                        "per_detector_scores"][name]["verdict"]
                    after = var["per_detector_scores"][name]["verdict"]
                    if before in self.ai and after in self.human:
                        flips += 1
                lo, hi = wilson_interval(flips, count, level)
                rate = flips / count
                cells.append({
                    "pipe": pipe, "detector": name, "n": count, "flips": flips,
                    "rate": rate, "lo": lo, "hi": hi,
                    "significant": bool(count >= min_n and rate >= min_rate
                                        and lo >= ci_bound)})
        return cells

    def triage_list(self, cells):
        pipe_rank = {p: i for i, p in enumerate(self.order)}
        det_rank = {d[0]: i for i, d in enumerate(self.detectors)}
        return sorted(
            [c for c in cells if c["flips"] > 0],
            key=lambda c: (-c["flips"], pipe_rank[c["pipe"]],
                           det_rank[c["detector"]]))

    def compute_all(self):
        values = {}
        low_n = cfg.require_resolved(self.reporting, "reporting_low_n_minimum",
                                     "config/reporting.yaml")
        values["det.count"] = str(len(self.detectors))
        values["stores.d2_n"] = str(len(self.d2))
        values["stores.d3_n"] = str(len(self.d3))
        values["stores.d3a_n"] = str(len(self.d3a))
        values["stores.originals_n"] = str(len(self.originals))
        values["stores.variants_n"] = str(len(self.d3) + len(self.d3a))
        manifest = read_json("datasets/v1/manifest.json")
        seen_labels = [s["ground_truth_label"] for s in manifest["samples"]]
        values["manifest.v1_samples"] = str(len(seen_labels))
        values["manifest.v1_ai"] = str(sum(1 for x in seen_labels if x == "ai"))
        values["manifest.v1_human"] = str(sum(1 for x in seen_labels if x == "human"))
        values["cfg.threshold"] = str(cfg.require_resolved(
            self.fidelity, "fidelity_threshold", "config/fidelity.yaml"))
        values["cfg.low_n"] = str(low_n)
        values["cfg.min_n"] = str(cfg.require_resolved(
            self.analysis, "analysis_minimum_n", "config/analysis.yaml"))
        values["cfg.min_rate"] = str(cfg.require_resolved(
            self.analysis, "analysis_minimum_rate", "config/analysis.yaml"))
        values["cfg.ci_bound"] = str(cfg.require_resolved(
            self.analysis, "analysis_ci_lower_bound", "config/analysis.yaml"))
        values["cfg.ci_level"] = str(cfg.require_resolved(
            self.analysis, "analysis_ci_level", "config/analysis.yaml"))
        sev_low, sev_med = self.severity_pair()
        values["cfg.sev_low"] = str(sev_low)
        values["cfg.sev_med"] = str(sev_med)
        values["cfg.fpr_bound"] = str(cfg.require_resolved(
            self.analysis, "analysis_human_fpr_bound", "config/analysis.yaml"))
        for short, key in (("s_min", "band_S_min_words"), ("s_max", "band_S_max_words"),
                           ("m_min", "band_M_min_words"), ("m_max", "band_M_max_words"),
                           ("l_min", "band_L_min_words"), ("l_max", "band_L_max_words")):
            values["cfg.band_%s" % short] = str(cfg.require_resolved(
                self.datasets, key, "config/datasets.yaml"))
        values["cfg.pipes_n"] = str(len(self.order))
        values["cfg.release_n"] = str(len(self.d6["d6_release_items"]))
        raw_short = {"Likely AI-generated": "likely_ai", "Slop detected": "slop_detected",
                     "Low risk": "low_risk", "Clean — likely human-written": "clean_human",
                     "Suspicious": "suspicious"}
        pooled = []
        medians = []
        for pipe in self.order:
            recs = self.grouped[pipe]
            ok = self.passing(pipe)
            total, passed = len(recs), len(ok)
            cos = sorted(v["fidelity"]["cosine"] for v in ok)
            pooled.extend(cos)
            med = statistics.median(cos)
            medians.append(round(med, self.frac_dec))
            buckets = {"ai": 0, "human": 0, "uncertain": 0}
            raw = {}
            for var in ok:
                verdict = (var.get("overall_verbatim") or {})["overall_verdict"]
                raw[verdict] = raw.get(verdict, 0) + 1
                buckets[self.overall_bucket(verdict)] += 1
            pre = "s3c.%s" % pipe
            values[pre + ".total_n"] = str(total)
            values[pre + ".passing_n"] = str(passed)
            values[pre + ".passing_rate"] = self.frac(passed / total)
            values[pre + ".overall_human_pct"] = self.pct(buckets["human"], passed)
            values[pre + ".overall_ai_pct"] = self.pct(buckets["ai"], passed)
            values[pre + ".overall_uncertain_pct"] = self.pct(buckets["uncertain"], passed)
            values[pre + ".fidelity_median"] = self.frac(med)
            values[pre + ".fidelity_spread"] = self.frac(max(cos) - min(cos))
            values[pre + ".spot_n"] = "0"
            values[pre + ".low_n"] = self.boolean(passed < low_n)
            values[pre + ".evidence_n"] = str(passed)
            for raw_val, short in raw_short.items():
                values["oc.%s.%s" % (pipe, short)] = str(raw.get(raw_val, 0))
            u_all = sorted(v["fidelity"]["cosine"] for v in recs)
            u_buckets = {"ai": 0, "human": 0, "uncertain": 0}
            for var in recs:
                verdict = (var.get("overall_verbatim") or {})["overall_verdict"]
                u_buckets[self.overall_bucket(verdict)] += 1
            upre = "unf.%s" % pipe
            values[upre + ".total_n"] = str(total)
            values[upre + ".overall_human_pct"] = self.pct(u_buckets["human"], total)
            values[upre + ".overall_ai_pct"] = self.pct(u_buckets["ai"], total)
            values[upre + ".overall_uncertain_pct"] = self.pct(u_buckets["uncertain"], total)
            values[upre + ".fidelity_median"] = self.frac(statistics.median(u_all))
            values[upre + ".fidelity_spread"] = self.frac(max(u_all) - min(u_all))
            values[upre + ".spot_n"] = "0"
            values[upre + ".low_n"] = self.boolean(total < low_n)
            values[upre + ".evidence_n"] = str(total)
            values["dist.%s.min" % pipe] = self.frac(min(cos))
            values["dist.%s.max" % pipe] = self.frac(max(cos))
            base_ids = sorted({v["original_id"] for v in recs})
            values["detect.%s.baseline_n" % pipe] = str(len(base_ids))
            for name, key in self.detectors:
                tallies = {"ai": 0, "human": 0, "uncertain": 0}
                for var in ok:
                    tallies[self.detector_bucket(
                        var["per_detector_scores"][name]["verdict"])] += 1
                dpre = "det.%s.%s" % (pipe, key)
                values[dpre + ".n"] = str(passed)
                values[dpre + ".human_pct"] = self.pct(tallies["human"], passed)
                values[dpre + ".ai_pct"] = self.pct(tallies["ai"], passed)
                values[dpre + ".uncertain_pct"] = self.pct(tallies["uncertain"], passed)
                values[dpre + ".evidence_n"] = str(passed)
                hit_v = sum(1 for var in ok if var["per_detector_scores"][name][
                    "verdict"] in self.ai)
                hit_b = sum(1 for sid in base_ids if self.originals[sid][
                    "per_detector_scores"][name]["verdict"] in self.ai)
                spre = "detect.%s.%s" % (pipe, key)
                values[spre + ".baseline_rate"] = self.frac(hit_b / len(base_ids))
                values[spre + ".variant_rate"] = self.frac(hit_v / passed)
                values[spre + ".delta"] = self.frac(hit_v / passed - hit_b / len(base_ids))
        values["dist.pooled_n"] = str(len(pooled))
        values["dist.overall_median"] = self.frac(statistics.median(pooled))
        values["dist.overall_min"] = self.frac(min(pooled))
        values["dist.overall_max"] = self.frac(max(pooled))
        values["dist.overall_spread"] = self.frac(max(pooled) - min(pooled))
        values["dist.median_min"] = self.frac(min(medians))
        values["dist.median_max"] = self.frac(max(medians))
        humans = sorted((r for r in self.originals.values()
                         if r["ground_truth_label"] == "human"),
                        key=lambda r: r["sample_id"])
        values["hum.n"] = str(len(humans))
        o_hum = {"ai": 0, "human": 0, "uncertain": 0}
        for name, key in self.detectors:
            tallies = {"ai": 0, "human": 0, "uncertain": 0}
            for rec in humans:
                tallies[self.detector_bucket(
                    rec["per_detector_scores"][name]["verdict"])] += 1
            hpre = "hum.%s" % key
            values[hpre + ".human_pct"] = self.pct(tallies["human"], len(humans))
            values[hpre + ".ai_pct"] = self.pct(tallies["ai"], len(humans))
            values[hpre + ".uncertain_pct"] = self.pct(tallies["uncertain"], len(humans))
        for rec in humans:
            verdict = (rec.get("overall_verbatim") or {})["overall_verdict"]
            o_hum[self.overall_bucket(verdict)] += 1
        values["hum.overall_human_pct"] = self.pct(o_hum["human"], len(humans))
        values["hum.overall_ai_pct"] = self.pct(o_hum["ai"], len(humans))
        values["hum.overall_uncertain_pct"] = self.pct(o_hum["uncertain"], len(humans))
        cells = self.cell_stats()
        sig = [c for c in cells if c["significant"]]
        values["modes.cells_n"] = str(len(cells))
        values["modes.sig_n"] = str(len(sig))
        values["modes.flips_total"] = str(sum(c["flips"] for c in cells))
        values["modes.max_flips"] = str(max(c["flips"] for c in cells))
        sig_by_pipe = {p: 0 for p in self.order}
        for cell in sig:
            sig_by_pipe[cell["pipe"]] += 1
        for pipe in self.order:
            values["sig.%s.n" % pipe] = str(sig_by_pipe[pipe])
        for i, cell in enumerate(self.triage_list(cells), 1):
            tpre = "triage.%d" % i
            values[tpre + ".rank"] = str(i)
            values[tpre + ".flips"] = str(cell["flips"])
            values[tpre + ".n"] = str(cell["n"])
            values[tpre + ".rate"] = self.frac(cell["rate"])
            values[tpre + ".ci_lo"] = self.frac(cell["lo"])
            values[tpre + ".ci_hi"] = self.frac(cell["hi"])
        entries = self.index_entries()
        values["fixes.n"] = str(len(entries))
        for entry in entries:
            short = entry["fix_id"].lower().replace("-", "")
            values["fixes.%s.detectors_n" % short] = str(len(entry["targets"]))
            values["fixes.%s.failures_n" % short] = str(len(entry["failures"]))
        values["reg.variants_rescored_n"] = str(len(self.d3) + len(self.d3a))
        drift = read_json("build/evidence/D5/drift-report.json")
        stats = drift["regen"]["stats"]
        values["reg.rescoring_pass"] = self.boolean(drift["rescoring"]["pass"])
        values["reg.drift_n"] = str(stats["n"])
        values["reg.drift_fid_mean"] = self.frac(stats["fidelity_mean"])
        values["reg.drift_fid_min"] = self.frac(stats["fidelity_min"])
        values["reg.drift_delta_mean"] = self.frac(stats["delta_mean"])
        values["reg.drift_delta_max"] = self.frac(stats["delta_max"])
        clean = read_json("build/evidence/D5/cleanroom-diff.json")["scores"]
        values["reg.cleanroom_compared_n"] = str(clean["compared"])
        values["reg.cleanroom_mismatches_n"] = str(len(clean["mismatches"]))
        values["reg.cleanroom_worst_d"] = self.frac(clean["worst_delta"])
        values["reg.d4_identical"] = self.boolean(
            drift["cleanroom"]["d4_report_identical"])
        values["reg.manifests_identical_n"] = str(sum(
            1 for m in drift["cleanroom"]["manifests_identical"].values()
            if m["identical_except_run_id"]))
        values["reg.fixes_differing_n"] = str(
            len(drift["cleanroom"]["fixes_tree"]["differing"]))
        values["reg.allowlist_n"] = str(drift["gate"]["allowlist_ids"])
        impl_run = cfg.require_resolved(self.d6, "d6_d5_impl_run_id", "config/d6.yaml")
        scan = read_json("build/evidence/D5/runs/%s/scan-report.json" % impl_run)
        values["reg.clis_n"] = str(len(scan["findings"]["cli_inventory"]))
        values["reg.docs_n"] = str(len(scan["scanned_docs"]))
        trace = read_json("build/evidence/D6/traceability.json")
        values["meta.numbers_n"] = str(len(trace["numbers"]))
        return values


def main(argv):
    if len(argv) != 2:
        print("usage: d6_recompute.py <number_id>", file=sys.stderr)
        return 2
    world = World()
    values = world.compute_all()
    if argv[1] not in values:
        print("unknown number_id: %s" % argv[1], file=sys.stderr)
        return 2
    print(values[argv[1]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
