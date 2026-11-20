"""D3A budget (independent path): per-invocation Bodhan audit attempts within
the config budget, and successful legs equal legs-per-pipeline x variants for
every D3A pipeline (expected counts derived from the pipeline defs, never
hardcoded).
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


def main(run_dir, store_dir, run_id):
    report = {"check": "d3a-budget", "pass": False, "details": []}
    pipes = cfg.load("pipelines.yaml")
    budget = cfg.require_resolved(cfg.load("bodhan.yaml"), "bodhan_max_calls", "config/bodhan.yaml")
    total_attempts, total_expected, total_orphans = 0, 0, 0
    for pipe in pipes["d3a_pipelines"]:
        audit = read_log(os.path.join(store_dir, "bodhan-audit-%s-%s.jsonl" % (run_id, pipe)))
        attempts = [e for e in audit if "attempt" in e]
        total_attempts += len(attempts)
        if len(attempts) > budget:
            report["details"].append("%s: %d attempts exceed %d" % (pipe, len(attempts), budget))
        legs = sum(1 for ref in pipes["pipeline_%s_steps" % pipe] if ref.startswith("bodhan-"))
        variants = len([f for f in os.listdir(os.path.join(store_dir, "records"))
                        if f.startswith("V-%s-" % pipe)])
        expected = legs * variants
        total_expected += expected
        # Blocked samples may hold orphan successes (legs that succeeded before
        # the sample failed), so partition by this run's blocked list: only
        # unblocked samples must account exactly.
        blocked_ids = {e["sample_id"] for e in json.load(open(os.path.join(
            store_dir, "blocked-%s-%s.json" % (run_id, pipe))))}
        successes = [e for e in audit if e.get("outcome") in ("scored", "reused")]
        orphans = [e for e in successes if e.get("sample_id") in blocked_ids]
        total_orphans += len(orphans)
        completed = [e for e in successes if e.get("sample_id") not in blocked_ids]
        if len(completed) != expected:
            report["details"].append("%s: %d completed successes != %d legs x %d variants (%d orphans on %d blocked)"
                                     % (pipe, len(completed), legs, variants,
                                        len(orphans), len(blocked_ids)))
    if not report["details"]:
        report["details"].append("%d attempts within budget; %d successes match defs (%d orphans on blocked)"
                                 % (total_attempts, total_expected, total_orphans))
    report["pass"] = not [d for d in report["details"] if "within budget" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3a-budget.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3a-budget: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
