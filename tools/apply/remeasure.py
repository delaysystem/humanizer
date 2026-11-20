"""Apply-phase re-measurement: score frozen texts against one isolated deployment.

Per entry: (0) boundary proof — witness texts from frozen stores whose
logged target-engine scores fall in each moved band are scored on BOTH
the baseline and the apply endpoint; verdicts must flip exactly as the
patch designs while every score, the overall score, and the flagged
count stay identical; (1) full scoring of the entry-condition variants
plus all 54 originals into new results/apply-<entry>/ dirs (frozen
records copied, score blocks replaced, fidelity/provenance kept);
(2) integrity asserts (scores + overall + flagged identical to frozen
for every record); (3) flip tables via the frozen flips.py CLI.
Resume-safe (frozen precedent: raw+record present means scored).
Usage: remeasure.py --entry FIX-D3A-001
"""
import argparse
import copy
import glob
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402
import run as runner  # noqa: E402 — frozen transport (pipeline.py precedent)
import store  # noqa: E402

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def health_ok(base, health_path):
    try:
        with urllib.request.urlopen(base + health_path, timeout=30) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 — health is boolean; failure returns False
        return False


def score_one(base, analyze, ticket_prefix, max_attempts, backoff, text, log, sid):
    report, fatal = runner.score_with_retry(
        base, analyze, ticket_prefix, text, max_attempts, backoff,
        runner.SCORE_TIMEOUT_S, lambda e: log.event(dict(e, sample_id=sid)))
    if report is None:
        raise ValueError("scoring blocked for %s: %s" % (sid, fatal))
    results = report.get("engine_results", [])
    if len(results) != 23:
        raise ValueError("%s: %d engine results, want 23" % (sid, len(results)))
    return report


def to_scores(report):
    return {e["engine_name"]: {"score": e["score"], "verdict": e["verdict"],
                               "details": e["details"]} for e in report["engine_results"]}


def to_overall(report):
    return {"overall_score": report.get("overall_score"),
            "overall_verdict": report.get("overall_verdict"),
            "engines_flagged": report.get("engines_flagged"),
            "engines_total": report.get("engines_total")}


def resolve_text(ref, kind):
    if kind == "variant":
        path = os.path.join(ROOT, "results/d3a", ref)
    else:
        path = os.path.join(ROOT, "datasets/v1", ref)
    if not os.path.isfile(path):
        raise ValueError("text missing: %s" % path)
    return open(path).read()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    args = ap.parse_args(argv)
    entry = args.entry
    apply_cfg = cfg.load("apply.yaml")
    if entry not in apply_cfg["apply_entries"]:
        raise ValueError("unknown entry " + entry)
    condition = cfg.require_resolved(apply_cfg, "apply_%s_condition" % entry,
                                     "config/apply.yaml")
    port = cfg.require_resolved(apply_cfg, "apply_%s_port" % entry, "config/apply.yaml")
    scheme = cfg.require_resolved(apply_cfg, "apply_url_scheme", "config/apply.yaml")
    base = "%s://localhost:%s" % (scheme, port)
    api = cfg.load("api.yaml")
    base0 = cfg.require_resolved(api, "sloptotal_base_url", "config/api.yaml")
    analyze = cfg.require_resolved(api, "sloptotal_analyze_path", "config/api.yaml")
    ticket_prefix = cfg.require_resolved(api, "sloptotal_ticket_path_prefix",
                                         "config/api.yaml")
    health_path = cfg.require_resolved(api, "sloptotal_health_path", "config/api.yaml")
    max_attempts = cfg.require_resolved(api, "runner_retry_max_attempts", "config/api.yaml")
    backoff = cfg.require_resolved(api, "runner_retry_backoff_s", "config/api.yaml")
    if not health_ok(base, health_path):
        raise ValueError("apply endpoint unhealthy: " + base)
    if not health_ok(base0, health_path):
        raise ValueError("baseline endpoint unhealthy: " + base0)
    inv = load_json(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json"))["payload"]["detectors"]
    name_of = {d["key"]: d["name"] for d in inv}
    manifest = load_json(os.path.join(
        ROOT, "build/evidence/APPLY/patch-%s/manifest.json" % condition))
    applied = manifest["applied"]
    if not applied:
        raise ValueError("no applied boundaries for " + condition)

    out = os.path.join(ROOT, "results/apply-" + entry)
    orig_out = os.path.join(ROOT, "results/apply-" + entry + "-originals")
    os.makedirs(out, exist_ok=True)
    os.makedirs(orig_out, exist_ok=True)
    run_tag = "apply-" + condition

    frozen_variants = []
    for path in sorted(glob.glob(os.path.join(
            ROOT, "results/d3a/records/V-%s-*.json" % condition))):
        frozen_variants.append(load_json(path))
    frozen_originals = []
    for path in sorted(glob.glob(os.path.join(
            ROOT, "results/d3a-originals/records/*.json"))):
        frozen_originals.append(load_json(path))
    if len(frozen_variants) != 27 or len(frozen_originals) != 54:
        raise ValueError("frozen counts %d/%d, want 27/54"
                         % (len(frozen_variants), len(frozen_originals)))

    # Step 0: boundary proof on witness texts, both endpoints.
    pool = frozen_variants + frozen_originals
    witness_log = store.AttemptLog(out, run_tag + "-witness")
    proofs = []
    for stem in sorted(applied):
        new_t = applied[stem]
        name = name_of[stem]
        if new_t > 0.65:
            band = (0.65, new_t)
            old_v, new_v = "slop", "suspicious"
        else:
            band = (new_t, 0.65)
            old_v, new_v = "suspicious", "slop"
        cands = [r for r in pool
                 if band[0] <= r["per_detector_scores"][name]["score"] < band[1]]
        if not cands:
            proofs.append({"engine": stem, "T": new_t, "witness": None,
                           "result": "UNWITNESSED-on-frozen-data"})
            continue
        rec = cands[0]
        kind = "variant" if rec["sample_id"].startswith("V-") else "original"
        text = resolve_text(rec["variant_text_ref"], kind)
        rep0 = score_one(base0, analyze, ticket_prefix, max_attempts, backoff,
                         text, witness_log, rec["sample_id"] + ":baseline")
        rep1 = score_one(base, analyze, ticket_prefix, max_attempts, backoff,
                         text, witness_log, rec["sample_id"] + ":apply")
        got0 = to_scores(rep0)[name]["verdict"]
        got1 = to_scores(rep1)[name]["verdict"]
        scores_same = all(to_scores(rep0)[n]["score"] == to_scores(rep1)[n]["score"]
                          for n, _k in [(d["name"], d["key"]) for d in inv])
        overall_same = (rep0.get("overall_score") == rep1.get("overall_score")
                        and rep0.get("engines_flagged") == rep1.get("engines_flagged"))
        ok = got0 == old_v and got1 == new_v and scores_same and overall_same
        proofs.append({"engine": stem, "T": new_t, "witness": rec["sample_id"],
                       "logged_score": rec["per_detector_scores"][name]["score"],
                       "baseline_verdict": got0, "apply_verdict": got1,
                       "scores_identical": scores_same,
                       "overall_identical": overall_same,
                       "result": "PROVEN" if ok else "MISMATCH"})
        if not ok:
            witness_log.close()
            raise ValueError("boundary proof failed for %s: %s" % (stem, proofs[-1]))
    witness_log.close()

    # Steps 1-2: full scoring with integrity asserts.
    log = store.AttemptLog(out, run_tag)
    olog = store.AttemptLog(orig_out, run_tag)
    scored, resumed = 0, 0
    for rec, kind, dest, alog in (
            [(r, "variant", out, log) for r in frozen_variants]
            + [(r, "original", orig_out, olog) for r in frozen_originals]):
        sid = rec["sample_id"]
        if os.path.exists(os.path.join(dest, "raw", sid + ".json")) and os.path.exists(
                os.path.join(dest, "records", sid + ".json")):
            resumed += 1
            continue
        text = resolve_text(rec["variant_text_ref"], kind)
        report = score_one(base, analyze, ticket_prefix, max_attempts, backoff,
                           text, alog, sid)
        new_scores = to_scores(report)
        for name in new_scores:
            if new_scores[name]["score"] != rec["per_detector_scores"][name]["score"]:
                raise ValueError("%s: score changed on %s" % (sid, name))
        new_overall = to_overall(report)
        for key in ("overall_score", "engines_flagged", "engines_total"):
            if new_overall[key] != rec["overall_verbatim"][key]:
                raise ValueError("%s: %s changed" % (sid, key))
        if new_overall["overall_verdict"] != rec["overall_verbatim"]["overall_verdict"]:
            raise ValueError("%s: overall verdict changed" % sid)
        store.write_raw(dest, sid, report)
        fresh = copy.deepcopy(rec)
        fresh["per_detector_scores"] = new_scores
        fresh["overall_verbatim"] = new_overall
        fresh["raw_report_id"] = report.get("id")
        fresh["apply_source"] = {"entry": entry, "condition": condition,
                                 "endpoint": base}
        store.write_record(dest, fresh)
        scored += 1
    log.close()
    olog.close()

    # Step 3: flip tables via the frozen CLI.
    done = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools/harness/flips.py"),
         "--store", out, "--originals", orig_out,
         "--out", os.path.join(out, "flip-tables-%s.json" % run_tag),
         "--ids-out", os.path.join(out, "failure-ids-%s.json" % run_tag)],
        cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        raise ValueError("flips.py failed: %s" % done.stderr.strip()[:300])
    evidence = {"entry": entry, "condition": condition, "endpoint": base,
                "applied": applied, "boundary_proofs": proofs,
                "scored": scored, "resumed": resumed,
                "flip_tables": "results/apply-%s/flip-tables-%s.json" % (entry, run_tag)}
    with open(os.path.join(ROOT, "build/evidence/APPLY/remeasure-%s.json" % entry),
              "w") as fh:
        json.dump(evidence, fh, indent=2, sort_keys=True)
    print("%s: proofs %d/%d proven, scored %d resumed %d" % (
        entry, sum(1 for p in proofs if p["result"] == "PROVEN"), len(proofs),
        scored, resumed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
