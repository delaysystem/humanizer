"""Runner CLI — harness entry point (D0 skeleton: init-run + score).

Config-driven: endpoint, paths, and probe text location come from config/*.yaml
via tools/harness/config.py. No literals for environment facts live here.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg
import evidence
import store

# origin: D0 decision — 15x provider typical max (8 s per sloptotal.com API page),
# valid post-first-scan; first scan warms in Probe 1, not in the suite.
SCORE_TIMEOUT_S = 120
# origin: D0 decision — D0 suite performs no score-changing retry; a transport
# failure fails the check honestly instead of being retried.
SCORE_ATTEMPTS = 1
# origin: D2 decision — ticket-poll cadence matching the D0 probe; only fires on
# HTTP 202 (busy/download-bound), which cached suite texts never trigger.
TICKET_POLL_S = 15
# origin: D2 decision — 10-minute ceiling for download-bound first scans.
TICKET_POLL_MAX = 40

PROJECT_ROOT = cfg.PROJECT_ROOT


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cmd_init_run(args):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tag = args.milestone.lower()
    run_id = "%s-%s-%s" % (stamp, tag, os.getpid())
    run_dir = os.path.join("build", "evidence", args.milestone, "runs", run_id)
    os.makedirs(os.path.join(PROJECT_ROOT, run_dir), exist_ok=True)
    config_files = []
    for base, _, files in os.walk(cfg.CONFIG_DIR):
        for name in sorted(files):
            if name.endswith((".yaml", ".json")):
                config_files.append(os.path.relpath(os.path.join(base, name), cfg.CONFIG_DIR))
    manifest = {
        "run_id": run_id,
        "milestone": args.milestone,
        "created_utc": evidence.utcnow(),
        "config_hashes": {f: sha256_file(os.path.join(cfg.CONFIG_DIR, f))
                          for f in sorted(config_files)},
        "probe_text_file": "tools/e2e/fixtures/probe-text.txt",
        "probe_text_sha256": sha256_file(
            os.path.join(PROJECT_ROOT, "tools/e2e/fixtures/probe-text.txt")),
    }
    evidence.write_json(os.path.join(run_dir, "manifest.json"), manifest, run_id)
    evidence.write_text(os.path.join(run_dir, "transcript.log"),
                        "run opened for milestone %s\n" % args.milestone, run_id)
    print(run_dir)
    return 0


def cmd_score(args):
    api = cfg.load("api.yaml")
    base = cfg.require_resolved(api, "sloptotal_base_url", "config/api.yaml")
    path = cfg.require_resolved(api, "sloptotal_analyze_path", "config/api.yaml")
    probe_text = open(os.path.join(PROJECT_ROOT, "tools/e2e/fixtures/probe-text.txt")).read()
    body = json.dumps({"text": probe_text}).encode()
    last_error = None
    for _ in range(SCORE_ATTEMPTS):
        req = urllib.request.Request(base + path, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=SCORE_TIMEOUT_S)
            raw = resp.read()
            status = resp.status
        except Exception as exc:  # transport failure: fail honestly, no retry
            last_error = "%s: %s" % (type(exc).__name__, exc)
            continue
        dt = round(time.time() - t0, 1)
        if status != 200:
            last_error = "HTTP %s" % status
            continue
        run_id = os.path.basename(os.path.normpath(args.run_dir))
        report = json.loads(raw)
        evidence.write_json(os.path.join(args.run_dir, "score-report.json"),
                            report, run_id)
        engines = report.get("engine_results", [])
        inv = json.load(open(os.path.join(
            PROJECT_ROOT, "build/evidence/D0/frozen/inventory.json")))
        by_name = {e["name"]: e["key"] for e in inv["payload"]["detectors"]}
        by_code = {e["code"]: e["key"] for e in inv["payload"]["detectors"]}
        scores_dir = os.path.join(args.run_dir, "scores")
        os.makedirs(os.path.join(PROJECT_ROOT, scores_dir), exist_ok=True)
        for item in engines:
            key = item.get("key") or by_code.get(item.get("code")) \
                or by_name.get(item.get("engine_name"))
            if not key:
                print("UNMAPPED_ENGINE_RESULT: %s" % item.get("engine_name"),
                      file=sys.stderr)
                return 3
            evidence.write_json(os.path.join(scores_dir, key + ".json"), item, run_id)
        print("scored engines: %d in %ss (http %s)" % (len(engines), dt, status))
        return 0
    print("SCORE_FAILED: %s" % last_error, file=sys.stderr)
    return 4


def _post(base, path, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read()), None
    except urllib.error.HTTPError as exc:
        return exc.code, None, "HTTP %s" % exc.code
    except Exception as exc:  # transport failure (DNS, refused, timeout, ...)
        return None, None, "%s: %s" % (type(exc).__name__, exc)


def _poll_ticket(base, prefix, ticket_id):
    url = base + prefix + ticket_id
    for poll in range(1, TICKET_POLL_MAX + 1):
        time.sleep(TICKET_POLL_S)
        try:
            resp = urllib.request.urlopen(url, timeout=60)
            data = json.loads(resp.read())
        except Exception as exc:
            return None, "ticket poll %d failed: %s" % (poll, exc)
        if isinstance(data, dict) and "engine_results" in data:
            return data, None
    return None, "ticket %s not ready after %d polls" % (ticket_id, TICKET_POLL_MAX)


def score_with_retry(base, analyze, ticket_prefix, text, max_attempts, backoff,
                     timeout, log_fn):
    """POST one text with bounded transport-error retries (identical params).

    Returns (report_or_None, fatal_or_None). Retries follow only transport
    errors (connection/timeout/429/5xx); HTTP 202 waits on its ticket once (not
    a retry); other statuses fail without retry. Every attempt and sleep is
    reported through log_fn (event shapes frozen — d2_retry parses them).
    """
    report, fatal = None, None
    for attempt in range(1, max_attempts + 1):
        status, data, error = _post(base, analyze, {"text": text}, timeout)
        log_fn({"attempt": attempt, "http": status,
                "outcome": error or ("ticket" if status == 202 else "scored"),
                "t_utc": evidence.utcnow()})
        if status == 200:
            return data, None
        if status == 202:
            ticket_id = str(data.get("id") or data.get("ticket_id") or data.get("ticket"))
            return _poll_ticket(base, ticket_prefix, ticket_id)
        retryable = status is None or status in (429, 500, 502, 503, 504)
        if not retryable:
            return None, error  # 4xx etc: request error, never retried
        fatal = error
        if attempt < max_attempts:
            log_fn({"event": "sleep", "seconds": backoff})
            time.sleep(backoff)
    return None, fatal


def cmd_score_batch(args):
    api = cfg.load("api.yaml")
    base = args.base_url or cfg.require_resolved(api, "sloptotal_base_url", "config/api.yaml")
    analyze = cfg.require_resolved(api, "sloptotal_analyze_path", "config/api.yaml")
    ticket_prefix = cfg.require_resolved(api, "sloptotal_ticket_path_prefix", "config/api.yaml")
    max_attempts = cfg.require_resolved(api, "runner_retry_max_attempts", "config/api.yaml")
    backoff = cfg.require_resolved(api, "runner_retry_backoff_s", "config/api.yaml")
    manifest = json.load(open(args.dataset_manifest))
    ds_dir = os.path.dirname(os.path.abspath(args.dataset_manifest))
    probe_set = json.load(open(args.probe_set))["samples"]
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    os.makedirs(args.out, exist_ok=True)
    if args.reps_dir:
        os.makedirs(args.reps_dir, exist_ok=True)
    log = store.AttemptLog(args.out, args.run_id)
    blocked = scored = skipped = 0
    blocked_entries = []
    for sid in probe_set:
        sample = by_id[sid]
        # Resume: metrology runs (reps_dir set) always re-score; baseline runs
        # skip samples whose raw report + record already exist, so a killed run
        # (reboot, container loss) continues instead of restarting. Blocked
        # samples have no outputs and are always retried.
        if args.reps_dir is None and os.path.exists(
                os.path.join(args.out, "raw", sid + ".json")) and os.path.exists(
                os.path.join(args.out, "records", sid + ".json")):
            skipped += 1
            continue
        text = open(os.path.join(ds_dir, sample["text_file"])).read()
        report, fatal = score_with_retry(
            base, analyze, ticket_prefix, text, max_attempts, backoff, SCORE_TIMEOUT_S,
            lambda e: log.event(dict(e, sample_id=sid)))
        if report is None:
            blocked_entries.append({"sample_id": sid, "status": "EXTERNAL-BLOCKED",
                                    "reason": fatal})
            blocked += 1
            continue
        if args.reps_dir:
            rep_reports = [report]  # rep 1 is the stored report: exactly N calls
            for rep in range(2, args.repeats + 1):
                rstatus, rdata, rerror = _post(base, analyze, {"text": text}, SCORE_TIMEOUT_S)
                log.event({"sample_id": sid, "rep": rep, "http": rstatus,
                           "outcome": rerror or "scored", "t_utc": evidence.utcnow()})
                if rdata is None:
                    blocked_entries.append({"sample_id": sid,
                                            "status": "EXTERNAL-BLOCKED",
                                            "reason": "rep %d: %s" % (rep, rerror)})
                    report = None
                    break
                rep_reports.append(rdata)
            if report is None:
                blocked += 1
                continue
            for i, rep_data in enumerate(rep_reports, 1):
                rep_path = os.path.join(args.reps_dir, sid, "rep%d.json" % i)
                os.makedirs(os.path.dirname(rep_path), exist_ok=True)
                with open(rep_path, "w") as fh:
                    json.dump(rep_data, fh, indent=2)
        store.write_raw(args.out, sid, report)
        record = {
            "sample_id": sid,
            "original_id": sid,
            "ground_truth_label": sample["ground_truth_label"],
            "condition_id": "none-baseline",
            "transform_params": {},
            "provenance": ["d2-baseline-scoring"],
            "variant_text_ref": sample["text_file"],
            "per_detector_scores": {e["engine_name"]: {"score": e["score"],
                                                       "verdict": e["verdict"],
                                                       "details": e["details"]}
                                    for e in report["engine_results"]},
            "fidelity": {"cosine_vs_original": 1.0,
                         "method": "identity-original-untransformed",
                         "fidelity_passing": True},
            "store_record_id": "%s-%s" % (args.store_tag, sid),
            "raw_report_id": report.get("id"),
            "overall_verbatim": {"overall_score": report.get("overall_score"),
                                 "overall_verdict": report.get("overall_verdict"),
                                 "engines_flagged": report.get("engines_flagged"),
                                 "engines_total": report.get("engines_total")},
        }
        store.write_record(args.out, record)
        scored += 1
    log.close()
    with open(os.path.join(args.out, "blocked-%s.json" % args.run_id), "w") as fh:
        json.dump(blocked_entries, fh, indent=2)
    print("batch done: scored=%d blocked=%d skipped=%d store=%s"
          % (scored, blocked, skipped, args.out))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(prog="run.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init-run")
    p_init.add_argument("--milestone", default="D0")
    p_init.set_defaults(func=cmd_init_run)
    p_score = sub.add_parser("score")
    p_score.add_argument("--run-dir", required=True)
    p_score.set_defaults(func=cmd_score)
    p_batch = sub.add_parser("score-batch")
    p_batch.add_argument("--probe-set", required=True)
    p_batch.add_argument("--dataset-manifest", required=True)
    p_batch.add_argument("--out", required=True)
    p_batch.add_argument("--run-id", required=True)
    p_batch.add_argument("--store-tag", required=True)
    p_batch.add_argument("--base-url", default=None)
    p_batch.add_argument("--repeats", type=int, default=1)
    p_batch.add_argument("--reps-dir", default=None)
    p_batch.set_defaults(func=cmd_score_batch)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
