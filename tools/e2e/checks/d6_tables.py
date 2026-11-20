"""D6 section-3C checks (independent path): completeness, sums, ordering,
evidence linkage, language, config-hash, LOW-N, and unfiltered-view shape
over the final tables plus the triage/fix/human extras. Full per-cell
recomputation belongs to d6-trace; this check verifies structure, order,
sums within rounding, linkage resolution, and the exact schema field sets.
"""
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg  # noqa: E402

PIPE_FIELDS = ("pipeline_id", "config_hash", "steps", "total_samples_N",
               "fidelity_passing_N", "fidelity_passing_rate", "overall_human_pct",
               "overall_ai_pct", "overall_uncertain_pct", "overall_basis",
               "fidelity_median", "fidelity_spread", "spot_check_pass_rate",
               "spot_check_N", "low_N_flag", "evidence_artifact_ids")
DET_FIELDS = ("pipeline_id", "detector_id", "detector_type", "fidelity_passing_N",
              "human_pct", "ai_pct", "uncertain_pct", "uncertain_basis",
              "evidence_artifact_ids")
TRIAGE_NOTE = "Triage order is not a recommendation and not a pipeline ranking."


def load_json(rel):
    with open(os.path.join(ROOT, rel)) as fh:
        return json.load(fh)


def expected_hash(pipes, pipe_id):
    refs = list(cfg.require_resolved(pipes, "pipeline_%s_steps" % pipe_id,
                                     "config/pipelines.yaml"))
    params = {}
    for ref in refs:
        name, _at, ver = ref.partition("@")
        par_file = cfg.require_resolved(pipes, "step_%s_%s_params" % (name, ver),
                                        "config/pipelines.yaml")
        params[ref] = cfg.load(par_file)
    if pipe_id.startswith("d3a-"):
        manifest = load_json("datasets/d3a/manifest-%s.json" % pipe_id)
        manifest = dict(manifest)
        manifest.pop("producing_run_id", None)
    else:
        sel = cfg.require_resolved(pipes, "pipeline_%s_samples" % pipe_id,
                                   "config/pipelines.yaml")
        manifest = {"manifest": "datasets/v1/manifest.json", "selector": sel,
                    "note": "D3 conditions draw from v1 directly (no per-condition manifest)"}
    canonical = json.dumps({"pipeline_id": pipe_id, "steps": refs,
                            "step_params": params, "dataset_manifest": manifest},
                           sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(run_dir):
    report = {"check": "d6-tables", "pass": False, "details": []}
    problems = []
    tables = load_json("build/evidence/D6/final-tables.json")
    pipes = cfg.load("pipelines.yaml")
    order = list(pipes["dataset_pipelines"]) + list(pipes["d3a_pipelines"])
    inv = load_json("build/evidence/D0/frozen/inventory.json")["payload"]["detectors"]
    det_names = [d["name"] for d in inv]
    det_types = {d["name"]: d["detector_type"] for d in inv}
    tols = cfg.load("tolerances.yaml")
    pct_tol = cfg.require_resolved(tols, "percentage_recompute_rounding",
                                   "config/tolerances.yaml")
    low_n = cfg.require_resolved(cfg.load("reporting.yaml"), "reporting_low_n_minimum",
                                 "config/reporting.yaml")
    d6 = cfg.load("d6.yaml")
    unc_basis = cfg.require_resolved(d6, "d6_uncertain_basis", "config/d6.yaml")

    per_pipe = tables["per_pipeline"]
    if [r["pipeline_id"] for r in per_pipe] != order:
        problems.append("per-pipeline order != config pipeline order")
    for row in per_pipe:
        if set(row) != set(PIPE_FIELDS):
            problems.append("%s: schema fields %s" % (row.get("pipeline_id"), sorted(set(row))))
            continue
        parts = [row["overall_human_pct"], row["overall_ai_pct"], row["overall_uncertain_pct"]]
        if abs(sum(parts) - 100.0) > len(parts) * pct_tol:
            problems.append("%s: overall shares sum %s" % (row["pipeline_id"], sum(parts)))
        if row["overall_basis"] != "sloptotal_combined_verbatim":
            problems.append("%s: bad overall_basis" % row["pipeline_id"])
        if row["low_N_flag"] != (row["fidelity_passing_N"] < low_n):
            problems.append("%s: LOW-N flag wrong" % row["pipeline_id"])
        if row["spot_check_pass_rate"] is not None or row["spot_check_N"] != 0:
            problems.append("%s: spot-check fields must be null/0" % row["pipeline_id"])
        if row["fidelity_passing_rate"] != round(
                row["fidelity_passing_N"] / row["total_samples_N"], 4):
            problems.append("%s: passing rate mismatch" % row["pipeline_id"])
        if row["config_hash"] != expected_hash(pipes, row["pipeline_id"]):
            problems.append("%s: config hash mismatch" % row["pipeline_id"])
        if len(row["evidence_artifact_ids"]) != row["fidelity_passing_N"]:
            problems.append("%s: evidence count != passing N" % row["pipeline_id"])
        for aid in row["evidence_artifact_ids"]:
            if not os.path.isfile(os.path.join(ROOT, aid)):
                problems.append("%s: missing artifact %s" % (row["pipeline_id"], aid))
                break

    per_det = tables["per_detector"]
    want_det = [(p, d) for p in order for d in det_names]
    if [(r["pipeline_id"], r["detector_id"]) for r in per_det] != want_det:
        problems.append("per-detector order != pipeline-major/inventory-minor")
    for row in per_det:
        if set(row) != set(DET_FIELDS):
            problems.append("detail row schema %s" % sorted(set(row)))
            continue
        parts = [row["human_pct"], row["ai_pct"], row["uncertain_pct"]]
        if abs(sum(parts) - 100.0) > len(parts) * pct_tol:
            problems.append("%s/%s: shares sum %s"
                            % (row["pipeline_id"], row["detector_id"], sum(parts)))
        if row["uncertain_basis"] != unc_basis:
            problems.append("%s/%s: uncertain_basis != config"
                            % (row["pipeline_id"], row["detector_id"]))
        if row["detector_type"] != det_types[row["detector_id"]]:
            problems.append("%s: detector_type != inventory" % row["detector_id"])
        if len(row["evidence_artifact_ids"]) != row["fidelity_passing_N"]:
            problems.append("%s/%s: evidence count != passing N"
                            % (row["pipeline_id"], row["detector_id"]))

    unfiltered = tables["unfiltered"]
    want_unf = {"pipeline_id"} | {k + "_unfiltered" for k in PIPE_FIELDS if k != "pipeline_id"}
    if [r["pipeline_id"] for r in unfiltered] != order:
        problems.append("unfiltered order != config pipeline order")
    for row in unfiltered:
        if set(row) != want_unf:
            problems.append("%s: unfiltered fields %s"
                            % (row.get("pipeline_id"), sorted(set(row))))
            continue
        parts = [row["overall_human_pct_unfiltered"], row["overall_ai_pct_unfiltered"],
                 row["overall_uncertain_pct_unfiltered"]]
        if abs(sum(parts) - 100.0) > len(parts) * pct_tol:
            problems.append("%s: unfiltered shares sum %s" % (row["pipeline_id"], sum(parts)))
        if len(row["evidence_artifact_ids_unfiltered"]) != row["total_samples_N_unfiltered"]:
            problems.append("%s: unfiltered evidence count != total" % row["pipeline_id"])
        filt = [r for r in per_pipe if r["pipeline_id"] == row["pipeline_id"]][0]
        if row["fidelity_passing_N_unfiltered"] != filt["fidelity_passing_N"]:
            problems.append("%s: unfiltered passing N != filtered" % row["pipeline_id"])
        if row["fidelity_passing_rate_unfiltered"] != filt["fidelity_passing_rate"]:
            problems.append("%s: unfiltered passing rate != filtered" % row["pipeline_id"])
        if row["overall_basis_unfiltered"] != filt["overall_basis"]:
            problems.append("%s: unfiltered basis != filtered" % row["pipeline_id"])

    store_conds = set()
    for store in ("results/d3", "results/d3a"):
        for path in glob.glob(os.path.join(ROOT, store, "records", "*.json")):
            store_conds.add(load_json(os.path.relpath(path, ROOT))["condition_id"])
    if store_conds != set(order):
        problems.append("store conditions %s != config pipelines" % sorted(store_conds))

    triage = tables["triage"]
    pipe_rank = {p: i for i, p in enumerate(order)}
    det_rank = {d: i for i, d in enumerate(det_names)}
    resorted = sorted(triage, key=lambda c: (-c["flips"], pipe_rank[c["pipeline_id"]],
                                             det_rank[c["detector_id"]]))
    if [(c["pipeline_id"], c["detector_id"]) for c in triage] != [
            (c["pipeline_id"], c["detector_id"]) for c in resorted]:
        problems.append("triage order != flip-count/pipeline/inventory order")
    if any(c["flips"] <= 0 for c in triage):
        problems.append("triage holds a zero-flip cell")
    if "flip" not in cfg.require_resolved(d6, "d6_triage_sort_key", "config/d6.yaml"):
        problems.append("triage key is not flip-count based")

    md = open(os.path.join(ROOT, "build", "FINAL-REPORT.md")).read()
    if TRIAGE_NOTE not in md:
        problems.append("triage header note missing")
    if "fidelity-passing flip count descending" not in md:
        problems.append("triage sort key not stated in report")
    sections = re.split(r"^## \d+\. ", md, flags=re.M)
    by_title = {}
    for chunk in sections[1:]:
        title = chunk.splitlines()[0].strip()
        by_title[title] = chunk

    def table_first_cells(chunk):
        cells, past_sep = [], False
        for line in chunk.splitlines():
            if not line.startswith("|"):
                continue
            if "---" in line:
                past_sep = True
                continue
            if past_sep:
                cells.append(line.split("|")[1].strip())
        return cells

    modes_cells = table_first_cells(by_title.get("Failure modes and fix linkage", ""))
    if modes_cells != order:
        problems.append("modes table order != pipeline order: %s" % modes_cells)
    hum_cells = table_first_cells(by_title.get("Human controls (caveated, not section 3C)", ""))
    if hum_cells != det_names:
        problems.append("human-controls order != inventory order")
    map_cells = table_first_cells(by_title.get("Overall-verdict mapping audit", ""))
    if map_cells != order:
        problems.append("mapping table order != pipeline order")

    d5 = cfg.load("d5.yaml")
    lang_res = [re.compile(w, re.IGNORECASE) for w in d5["d5_gate_evasion_words"]]
    lang_res += [re.compile(re.escape(p), re.IGNORECASE)
                 for p in d5["d5_gate_recommendation_phrases"]]
    lang_hits, quote_hits = [], []
    in_fence = False
    for lineno, line in enumerate(md.splitlines(), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        quoted = line.lstrip().startswith(">")
        scrubbed = re.sub(r"`[^`]*`", "", line)
        for rx in lang_res:
            if rx.search(scrubbed):
                (quote_hits if quoted else lang_hits).append(
                    "%d:%s" % (lineno, line.strip()[:100]))
    if lang_hits:
        problems.append("%d language hits: %s" % (len(lang_hits), "; ".join(lang_hits[:5])))

    blocked = load_json("build/evidence/D6/blocked-items.json")["items"]
    b003 = [b for b in blocked if b["item_id"] == "B-003"]
    if not b003 or "spot" not in b003[0]["effect"].lower():
        problems.append("B-003 missing or lacks the spot-check effect")

    if problems:
        report["details"].append("%d table problems: %s" % (len(problems), "; ".join(problems[:8])))
    else:
        report["details"].append(
            "8 pipe + 184 detail + 8 unfiltered rows verified; sums/order/linkage/hash/LOW-N clean; "
            "triage ordered + noted; %d quote-line language citations (allowed)" % len(quote_hits))
        report["pass"] = True
    report["quote_language_citations"] = quote_hits
    json.dump(report, open(os.path.join(run_dir, "check-d6-tables.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d6-tables: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
