"""D3 E2E-2c (independent path): Bodhan failure handling — the fault-probe sample
(a real HTTP 400 from an invalid code) is EXTERNAL-BLOCKED with its reason,
produced no variant record, and was attempted exactly once (no retry, hence no
parameter change). Any main-run blocked samples must show the same discipline:
transport-error attempts only, identical params across attempts.
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
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(run_dir, dead_store, run_id, main_store):
    report = {"check": "d3-bodhan-fault", "pass": False, "details": []}
    blocked = json.load(open(os.path.join(
        dead_store, "blocked-%s-probe-bodhan-fault.json" % run_id)))
    if len(blocked) != 1 or blocked[0].get("status") != "EXTERNAL-BLOCKED":
        report["details"].append("fault sample not exactly-once blocked: %s" % blocked)
    elif "400" not in str(blocked[0].get("reason", "")):
        report["details"].append("fault reason is not the 400: %s" % blocked[0].get("reason"))
    audit = read_log(os.path.join(
        dead_store, "bodhan-audit-%s-probe-bodhan-fault.jsonl" % run_id))
    attempts = [e for e in audit if "attempt" in e]
    if len(attempts) != 1:
        report["details"].append("fault attempts %d != 1" % len(attempts))
    if os.path.exists(os.path.join(dead_store, "records")):
        report["details"].append("fault run wrote score records")
    if os.path.exists(os.path.join(dead_store, "variants")):
        report["details"].append("fault run wrote variants")
    # Main-run blocked samples (if any): transport errors, identical params.
    main_blocked = json.load(open(os.path.join(
        main_store, "blocked-%s-cond-rt-kn.json" % run_id)))
    if main_blocked:
        main_audit = read_log(os.path.join(
            main_store, "bodhan-audit-%s-cond-rt-kn.jsonl" % run_id))
        for entry in main_blocked:
            sid = entry["sample_id"]
            tries = [e for e in main_audit if e.get("sample_id") == sid and "attempt" in e]
            if not tries or any(t.get("http") is not None and t.get("http") not in
                                (429, 500, 502, 503, 504) for t in tries):
                report["details"].append("%s: blocked without transport-error basis" % sid)
            echoes = {json.dumps(t.get("params_echo"), sort_keys=True) for t in tries}
            if len(echoes) != 1:
                report["details"].append("%s: params changed across attempts" % sid)
        report["details"].append("%d main-run blocked samples all disciplined"
                                 % len(main_blocked))
    else:
        report["details"].append("fault probe blocked-on-400 with 1 attempt; main run had 0 blocked")
    report["pass"] = not [d for d in report["details"]
                          if "blocked-on-400" not in d and "all disciplined" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-bodhan-fault.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-bodhan-fault: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
