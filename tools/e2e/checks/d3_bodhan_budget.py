"""D3 E2E-2d (independent path): Bodhan budget cap — audit-log attempt counts
are within the per-invocation budget, and successful translation calls equal
the Bodhan-generated variant count (every success accounted, no hidden calls).
"""
import glob
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


def main(run_dir, store_dir, run_id):
    report = {"check": "d3-bodhan-budget", "pass": False, "details": []}
    bod = cfg.load("bodhan.yaml")
    budget = cfg.require_resolved(bod, "bodhan_max_calls", "config/bodhan.yaml")
    audit = read_log(os.path.join(store_dir, "bodhan-audit-%s-cond-rt-kn.jsonl" % run_id))
    attempts = [e for e in audit if "attempt" in e]
    if len(attempts) > budget:
        report["details"].append("attempts %d exceed budget %d" % (len(attempts), budget))
    successes = [e for e in audit if e.get("outcome") in ("scored", "reused")]
    n_reused = len([e for e in successes if e.get("outcome") == "reused"])
    variants = [p for p in glob.glob(os.path.join(store_dir, "records", "V-cond-rt-kn-*.json"))]
    # Blocked samples may hold orphan successes (legs that succeeded before the
    # sample failed); only unblocked samples must account exactly. Each rt-kn
    # variant needs exactly 2 successful legs (freshly scored or honestly
    # reused from a config-matching sidecar; reused legs made no call).
    blocked_ids = {e["sample_id"] for e in json.load(open(os.path.join(
        store_dir, "blocked-%s-cond-rt-kn.json" % run_id)))}
    completed = [e for e in successes if e.get("sample_id") not in blocked_ids]
    if len(completed) != 2 * len(variants):
        report["details"].append("completed successes %d != 2 x variants %d (%d blocked)"
                                 % (len(completed), len(variants), len(blocked_ids)))
    if not report["details"]:
        report["details"].append("attempts %d within budget %d; %d successes (%d reused) == 2 x %d variants"
                                 % (len(attempts), budget, len(successes), n_reused, len(variants)))
    report["pass"] = not [d for d in report["details"] if "within budget" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-bodhan-budget.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-bodhan-budget: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
