"""D2 E2E-3 (independent path): determinism spread within tolerance.

Reads the N repeat reports per probe text from the run dir, computes per-text
per-detector min/max/range, and asserts every range is within
score_rerun_tolerance. Report IDs are recorded for cache transparency.
"""
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def main(run_dir, reps_dir, probe_set_path):
    report = {"check": "d2-spread", "pass": False, "details": []}
    tol = cfg.load("tolerances.yaml")
    spread_tol = cfg.require_resolved(tol, "score_rerun_tolerance", "config/tolerances.yaml")
    repeat_n = cfg.require_resolved(tol, "determinism_repeat_n", "config/tolerances.yaml")
    probe = json.load(open(probe_set_path))["samples"]
    table = {}
    for sid in probe:
        rep_files = [os.path.join(reps_dir, sid, "rep%d.json" % i)
                     for i in range(1, repeat_n + 1)]
        missing = [f for f in rep_files if not os.path.isfile(f)]
        if missing:
            report["details"].append("%s: missing reps %s" % (sid, missing))
            continue
        reps = [json.load(open(f)) for f in rep_files]
        ids = sorted({r.get("id") for r in reps})
        per_detector = {}
        for name in (e["engine_name"] for e in reps[0]["engine_results"]):
            vals = []
            for rep in reps:
                hit = [e["score"] for e in rep["engine_results"] if e["engine_name"] == name]
                if len(hit) != 1:
                    report["details"].append("%s: engine %s count %d" % (sid, name, len(hit)))
                    continue
                vals.append(hit[0])
            per_detector[name] = {"min": min(vals), "max": max(vals),
                                  "range": round(max(vals) - min(vals), 6)}
            if per_detector[name]["range"] > spread_tol:
                report["details"].append("%s %s: range %s exceeds %s"
                                         % (sid, name, per_detector[name]["range"], spread_tol))
        table[sid] = {"report_ids": ids, "repeat_n": len(reps), "per_detector": per_detector}
    json.dump(table, open(os.path.join(run_dir, "spread-table.json"), "w"), indent=2)
    if not report["details"]:
        report["details"].append("%d texts x %d reps: all ranges within %s"
                                 % (len(probe), repeat_n, spread_tol))
    report["pass"] = not [d for d in report["details"] if "within" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d2-spread.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d2-spread: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
