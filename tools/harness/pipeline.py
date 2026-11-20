"""§3B pipeline runner — config-declared test-variant pipelines (D3 build).

Usage: pipeline.py run --pipeline <id> --dataset-manifest <p> --out <dir>
  --run-id <id> --store-tag <tag> [--no-gate] [--no-score]

Fixed composition: pipelines, steps, versions, params, and sample selectors
come from config/pipelines.yaml + config/steps/*.yaml. Step modules resolve
through the fixed MODULES dict below (code review adds entries — never dynamic
loads of untrusted code). The fidelity gate runs after the full pipeline, never
between steps (§3B rule 3). Probe pipelines skip gate/score via flags and write
run-scoped out dirs only (asserted by checks, never the dataset store).

Resume (default on; --no-reuse disables): a sample whose variant text plus
sidecar exist and match the current config (step refs + full config hashes +
variant sha) reuses the stored text with zero provider calls — the transform
steps are skipped, the provenance chain is restored verbatim from the sidecar,
and the per-leg audit entries are recorded with outcome "reused" (no "attempt"
key, never counted against the call budget). Gate, scoring, and all per-run
files always execute fresh. A sample with no (or stale) sidecar regenerates.
The sidecar is written after gate/intermediates and before scoring, so a kill
anywhere resumes correctly: pre-sidecar kills regenerate, post-sidecar kills
reuse the text and re-score.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg
import evidence
import fidelity
import langcheck
import run as runner
import steps_bodhan
import steps_truncate
import steps_truncate_v2
import store

MODULES = {"steps_bodhan": steps_bodhan,
           "steps_truncate": steps_truncate,
           "steps_truncate_v2": steps_truncate_v2}


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _config_hashes():
    hashes = {}
    for base, _, files in os.walk(cfg.CONFIG_DIR):
        for name in sorted(files):
            if name.endswith((".yaml", ".json")):
                full = os.path.join(base, name)
                hashes[os.path.relpath(full, cfg.CONFIG_DIR)] = _sha256_file(full)
    return hashes


def _sidecar_valid(sidecar_path, variant_path, pipe_id, step_refs, hashes):
    try:
        side = json.load(open(sidecar_path))
    except (OSError, ValueError):
        return None
    if not isinstance(side, dict):
        return None
    if side.get("pipeline") != pipe_id:
        return None
    if side.get("steps") != step_refs:
        return None
    if side.get("config_hashes") != hashes:
        return None
    if side.get("variant_sha256") != _sha256_file(variant_path):
        return None
    if not isinstance(side.get("chain"), list):
        return None
    return side


def _select(manifest, selector):
    samples = manifest["samples"]
    if selector == "all-ai":
        return sorted(s["sample_id"] for s in samples if s["ground_truth_label"] == "ai")
    if selector == "ai-bands-M-L":
        return sorted(s["sample_id"] for s in samples
                      if s["ground_truth_label"] == "ai" and s["length_band"] in ("M", "L"))
    if selector == "first-ai-S":
        ids = sorted(s["sample_id"] for s in samples
                     if s["ground_truth_label"] == "ai" and s["length_band"] == "S")
        return ids[:1]
    raise ValueError("unknown sample selector: " + selector)


def _resolve_pipeline(pipe_id):
    pipes = cfg.load("pipelines.yaml")
    max_len = cfg.require_resolved(pipes, "max_pipeline_length", "config/pipelines.yaml")
    refs = cfg.require_resolved(pipes, "pipeline_%s_steps" % pipe_id, "config/pipelines.yaml")
    if len(refs) > max_len:
        raise ValueError("pipeline %s exceeds max length %d" % (pipe_id, max_len))
    steps = []
    for ref in refs:
        name, version = ref.split("@")
        key = "step_%s_v%s" % (name, version.lstrip("v"))
        module_name = cfg.require_resolved(pipes, key + "_module", "config/pipelines.yaml")
        params_file = cfg.require_resolved(pipes, key + "_params", "config/pipelines.yaml")
        if module_name not in MODULES:
            raise ValueError("unregistered step module: " + module_name)
        params = cfg.load(params_file)
        steps.append({"ref": ref, "name": name, "version": version,
                      "module": MODULES[module_name], "params": params})
    return pipes, steps


def cmd_run(args):
    pipes, steps = _resolve_pipeline(args.pipeline)
    samples_sel = cfg.require_resolved(pipes, "pipeline_%s_samples" % args.pipeline,
                                       "config/pipelines.yaml")
    round_every = pipes.get("pipeline_%s_round_every" % args.pipeline)
    fid_cfg = cfg.load("fidelity.yaml")
    # origin: D3A decision — d3a-* pipelines carry the extended gate readout;
    # all other pipelines carry v1 (same pass rule; see config/fidelity.yaml).
    gate_version = fid_cfg["gate_version_d3a"] if args.pipeline.startswith("d3a-") \
        else fid_cfg["gate_version_d3"]
    manifest = json.load(open(args.dataset_manifest))
    ds_dir = os.path.dirname(os.path.abspath(args.dataset_manifest))
    sample_ids = _select(manifest, samples_sel)
    if args.only_samples:
        want = [s.strip() for s in args.only_samples.split(",") if s.strip()]
        unknown = [s for s in want if s not in sample_ids]
        if unknown:
            raise ValueError("--only-samples lists non-selected samples: %s" % unknown)
        sample_ids = [s for s in sample_ids if s in set(want)]
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    api = cfg.load("api.yaml")
    bod = cfg.load("bodhan.yaml")
    os.makedirs(args.out, exist_ok=True)
    key_name = cfg.require_resolved(bod, "bodhan_key_env_var", "config/bodhan.yaml")
    key = os.environ.get(key_name, "")
    if any(s["module"] is steps_bodhan for s in steps) and not key:
        print("missing %s in environment" % key_name, file=sys.stderr)
        return 2
    audit_path = os.path.join(args.out, "bodhan-audit-%s-%s.jsonl" % (args.run_id, args.pipeline))
    audit_fh = open(audit_path, "w")
    ctx = {"key": key, "calls": 0,
           "max_calls": cfg.require_resolved(bod, "bodhan_max_calls", "config/bodhan.yaml"),
           "max_attempts": cfg.require_resolved(api, "runner_retry_max_attempts", "config/api.yaml"),
           "backoff": cfg.require_resolved(api, "runner_retry_backoff_s", "config/api.yaml"),
           "call_delay": cfg.require_resolved(bod, "bodhan_inter_call_delay_s",
                                              "config/bodhan.yaml"),
           "backoff_429": cfg.require_resolved(bod, "bodhan_429_backoff_s",
                                               "config/bodhan.yaml"),
           "base_url": cfg.require_resolved(bod, "bodhan_base_url", "config/bodhan.yaml"),
           "chat_path": cfg.require_resolved(bod, "bodhan_chat_path", "config/bodhan.yaml"),
           "model": cfg.require_resolved(bod, "bodhan_model", "config/bodhan.yaml"),
           "audit": lambda e: (audit_fh.write(json.dumps(e) + "\n"), audit_fh.flush())}
    model = fidelity.load_model() if args.gate else None
    scoring_log = store.AttemptLog(args.out, "%s-%s" % (args.run_id, args.pipeline)) if args.score else None
    base = cfg.require_resolved(api, "sloptotal_base_url", "config/api.yaml")
    analyze = cfg.require_resolved(api, "sloptotal_analyze_path", "config/api.yaml")
    ticket_prefix = cfg.require_resolved(api, "sloptotal_ticket_path_prefix", "config/api.yaml")
    counts = {"scored": 0, "blocked": 0, "degraded": 0, "reused": 0}
    hashes = _config_hashes()
    step_refs = [s["ref"] for s in steps]
    blocked_entries, degraded_ids = [], []
    for sid in sample_ids:
        sample = by_id[sid]
        original = open(os.path.join(ds_dir, sample["text_file"])).read()
        metadata = {"original_id": sid, "ground_truth_label": sample["ground_truth_label"],
                    "condition_id": args.pipeline, "provenance": []}
        vid = "V-%s-%s" % (args.pipeline, sid)
        variant_rel = os.path.join("variants", vid + ".txt")
        variant_path = os.path.join(args.out, variant_rel)
        sidecar_path = variant_path + ".meta.json"
        reused, text, snapshots = False, original, []
        if args.reuse and os.path.exists(variant_path) and os.path.exists(sidecar_path):
            side = _sidecar_valid(sidecar_path, variant_path, args.pipeline,
                                  step_refs, hashes)
            if side is not None:
                text = open(variant_path).read()
                metadata["provenance"] = side["chain"]
                for step in steps:
                    if step["module"] is steps_bodhan:
                        ctx["audit"]({"sample_id": sid, "step": step["name"],
                                      "outcome": "reused",
                                      "params_echo": {
                                          "target_language_code":
                                              step["params"]["target_language_code"],
                                          "target_script":
                                              step["params"].get("target_script", "native")},
                                      "variant_sha256": side["variant_sha256"]})
                reused = True
                counts["reused"] += 1
        if not reused:
            try:
                for i, step in enumerate(steps, 1):
                    metadata["current_step"] = step["name"]
                    metadata["current_version"] = step["version"]
                    text, metadata = step["module"].run(text, metadata, step["params"], ctx)
                    if round_every and i % round_every == 0:
                        snapshots.append(text)
            except steps_bodhan.BudgetExceeded as exc:
                print("BUDGET EXCEEDED, aborting run: %s" % exc, file=sys.stderr)
                return 5
            except steps_bodhan.BodhanError as exc:
                blocked_entries.append({"sample_id": sid, "pipeline": args.pipeline,
                                        "status": "EXTERNAL-BLOCKED", "reason": str(exc)[:300]})
                counts["blocked"] += 1
                continue
            os.makedirs(os.path.dirname(variant_path), exist_ok=True)
            with open(variant_path, "w") as fh:
                fh.write(text)
        chain = metadata["provenance"]
        if sample["ground_truth_label"] != metadata["ground_truth_label"]:
            print("LABEL MUTATION by pipeline", file=sys.stderr)
            return 6
        fidel = None
        if args.gate:
            fidel = fidelity.gate(original, text, model=model)
            fidel["gate_version"] = gate_version
            if args.pipeline.startswith("d3a-"):
                lang = langcheck.check(text)
                fidel["language"] = lang
                if lang["mismatch"]:
                    fidel["fidelity_passing"] = False
                    fidel["degraded_reason"] = "language_mismatch"
            if snapshots:
                inter_dir = os.path.join(args.out, "intermediates", vid)
                os.makedirs(inter_dir, exist_ok=True)
                rounds = []
                for r, snap in enumerate(snapshots, 1):
                    with open(os.path.join(inter_dir, "round%d.txt" % r), "w") as fh:
                        fh.write(snap)
                    rf = fidelity.gate(original, snap, model=model)
                    rounds.append({"round": r, "cosine": rf["cosine"],
                                   "passing": rf["fidelity_passing"],
                                   "file": "intermediates/%s/round%d.txt" % (vid, r)})
                with open(os.path.join(inter_dir, "rounds.json"), "w") as fh:
                    json.dump({"variant_id": vid, "rounds": rounds}, fh, indent=2)
            if not fidel["fidelity_passing"]:
                counts["degraded"] += 1
                degraded_ids.append(vid)
        if args.reuse and not reused:
            with open(sidecar_path, "w") as fh:
                json.dump({"variant_id": vid, "pipeline": args.pipeline,
                           "steps": step_refs, "config_hashes": hashes,
                           "variant_sha256": _sha256_file(variant_path),
                           "chain": chain}, fh, indent=2)
        if not args.score:
            counts["scored"] += 1  # probe run: generation completed, no scoring
            continue
        report, fatal = runner.score_with_retry(
            base, analyze, ticket_prefix, text, ctx["max_attempts"], ctx["backoff"],
            runner.SCORE_TIMEOUT_S,
            lambda e: scoring_log.event(dict(e, sample_id=vid)))
        if report is None:
            blocked_entries.append({"sample_id": sid, "variant_id": vid,
                                    "pipeline": args.pipeline,
                                    "status": "EXTERNAL-BLOCKED", "reason": str(fatal)[:300]})
            counts["blocked"] += 1
            continue
        store.write_raw(args.out, vid, report)
        record = {
            "sample_id": vid,
            "original_id": sid,
            "ground_truth_label": sample["ground_truth_label"],
            "condition_id": args.pipeline,
            "transform_params": {"pipeline": args.pipeline,
                                 "steps": [{"step": c["step"], "version": c["version"],
                                            "params": c["params"]} for c in chain]},
            "provenance": chain,
            "variant_text_ref": variant_rel,
            "per_detector_scores": {e["engine_name"]: {"score": e["score"],
                                                       "verdict": e["verdict"],
                                                       "details": e["details"]}
                                    for e in report["engine_results"]},
            "fidelity": fidel,
            "store_record_id": "%s-%s" % (args.store_tag, vid),
            "raw_report_id": report.get("id"),
            "overall_verbatim": {"overall_score": report.get("overall_score"),
                                 "overall_verdict": report.get("overall_verdict"),
                                 "engines_flagged": report.get("engines_flagged"),
                                 "engines_total": report.get("engines_total")},
        }
        store.write_record(args.out, record)
        counts["scored"] += 1
    audit_fh.close()
    if scoring_log:
        scoring_log.close()
    with open(os.path.join(args.out, "blocked-%s-%s.json" % (args.run_id, args.pipeline)), "w") as fh:
        json.dump(blocked_entries, fh, indent=2)
    with open(os.path.join(args.out, "excluded-%s-%s.json" % (args.run_id, args.pipeline)), "w") as fh:
        json.dump({"pipeline": args.pipeline, "degraded_variant_ids": sorted(degraded_ids)}, fh,
                  indent=2)
    if args.pipeline.startswith("d3a-") and args.manifest:
        ds_dir = os.path.join(cfg.PROJECT_ROOT, "datasets", "d3a")
        os.makedirs(ds_dir, exist_ok=True)
        cosines = []
        for rid in sorted(os.listdir(os.path.join(args.out, "records"))):
            if rid.startswith("V-%s-" % args.pipeline):
                rec = json.load(open(os.path.join(args.out, "records", rid)))
                if rec.get("fidelity") and "cosine" in rec["fidelity"]:
                    cosines.append(rec["fidelity"]["cosine"])
        cosines.sort()
        manifest_out = {
            "dataset_version": "%s-v1" % args.pipeline,
            "condition": args.pipeline,
            "params": [{"step": s["ref"], "params": s["params"]} for s in steps],
            "sample_count": len(sample_ids),
            "variant_count": counts["scored"],
            "degraded_count": counts["degraded"],
            "fidelity": {"median_cosine": cosines[len(cosines) // 2] if cosines else None,
                         "min_cosine": cosines[0] if cosines else None,
                         "gate_version": gate_version},
            "intensities": pipes.get("d3a_intensities"),
            "producing_run_id": args.run_id,
        }
        with open(os.path.join(ds_dir, "manifest-%s.json" % args.pipeline), "w") as fh:
            json.dump(manifest_out, fh, indent=2)
    evidence.write_json(os.path.join(args.out, "audit-%s-%s.json" % (args.run_id, args.pipeline)),
                        {"pipeline": args.pipeline,
                         "config_hashes": hashes,
                         "steps": [s["ref"] for s in steps],
                         "input_manifest_sha256": _sha256_file(args.dataset_manifest),
                         "sample_count": len(sample_ids),
                         "counts": counts,
                         "bodhan_calls": ctx["calls"]}, args.run_id)
    print("pipeline %s done: %s (bodhan calls %d)" % (args.pipeline, counts, ctx["calls"]))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(prog="pipeline.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--pipeline", required=True)
    p_run.add_argument("--dataset-manifest", required=True)
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--run-id", required=True)
    p_run.add_argument("--store-tag", required=True)
    p_run.add_argument("--gate", dest="gate", action=argparse.BooleanOptionalAction, default=True)
    p_run.add_argument("--score", dest="score", action=argparse.BooleanOptionalAction, default=True)
    p_run.add_argument("--reuse", dest="reuse", action=argparse.BooleanOptionalAction, default=True)
    p_run.add_argument("--only-samples", default=None,
                       help="comma-separated subset of selected sample IDs (D5 drift regen)")
    p_run.add_argument("--manifest", dest="manifest", action=argparse.BooleanOptionalAction,
                       default=True, help="write datasets/d3a manifest (disable for regen)")
    p_run.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
