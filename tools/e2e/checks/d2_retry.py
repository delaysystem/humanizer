"""D2 E2E-4 (independent path): no score-changing retry.

Parses both request logs. Dead-port log: every retry follows a logged
transport error (http null), uses the config backoff, attempts per sample ==
runner_retry_max_attempts, samples end EXTERNAL-BLOCKED with zero scores.
Normal log: every sample scores on attempt 1 — zero retries after success.
"""
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def read_log(path):
    return [json.loads(line) for line in open(path) if line.strip()]


def main(run_dir, normal_log, dead_log, dead_store):
    report = {"check": "d2-retry", "pass": False, "details": []}
    api = cfg.load("api.yaml")
    max_attempts = cfg.require_resolved(api, "runner_retry_max_attempts", "config/api.yaml")
    backoff = cfg.require_resolved(api, "runner_retry_backoff_s", "config/api.yaml")
    # Dead-port log: bounded transport-error retries only.
    dead = read_log(dead_log)
    attempts = [e for e in dead if "attempt" in e]
    sleeps = [e for e in dead if e.get("event") == "sleep"]
    by_sample = {}
    for event in attempts:
        by_sample.setdefault(event["sample_id"], []).append(event)
    for sid, events in sorted(by_sample.items()):
        if len(events) != max_attempts:
            report["details"].append("%s: %d attempts != %d" % (sid, len(events), max_attempts))
        for event in events:
            if event.get("http") is not None or "outcome" not in event:
                report["details"].append("%s: non-transport retry basis" % sid)
    for event in sleeps:
        if event.get("seconds") != backoff:
            report["details"].append("sleep != backoff: %s" % event)
    if len(sleeps) != len(by_sample) * (max_attempts - 1):
        report["details"].append("sleep count %d != expected %d"
                                 % (len(sleeps), len(by_sample) * (max_attempts - 1)))
    run_id = os.path.basename(os.path.normpath(run_dir))
    blocked = json.load(open(os.path.join(dead_store, "blocked-%s.json" % run_id)))
    if {b["sample_id"] for b in blocked} != set(by_sample):
        report["details"].append("dead-port blocked set != attempted set")
    if any(b.get("status") != "EXTERNAL-BLOCKED" for b in blocked):
        report["details"].append("dead-port non-blocked status present")
    if os.path.exists(os.path.join(dead_store, "records")):
        report["details"].append("dead-port run wrote score records")
    # Normal log: zero retries after success.
    normal = read_log(normal_log)
    normal_attempts = [e for e in normal if "attempt" in e]
    for event in normal_attempts:
        if event.get("attempt") != 1 or event.get("outcome") != "scored":
            report["details"].append("normal run retried or unscored: %s" % event)
    if [e for e in normal if e.get("event") == "sleep"]:
        report["details"].append("normal run slept (retried)")
    if not report["details"]:
        report["details"].append("dead-port: %d samples x %d transport-error attempts + backoff; "
                                 "normal: all first-attempt scored, zero retries"
                                 % (len(by_sample), max_attempts))
    report["pass"] = not [d for d in report["details"] if not d.startswith("dead-port:")]
    json.dump(report, open(os.path.join(run_dir, "check-d2-retry.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d2-retry: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
