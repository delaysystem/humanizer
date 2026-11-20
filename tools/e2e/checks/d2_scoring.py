"""D2 E2E-1 (independent path): stored scores equal raw responses field-for-field.

For each probe-set sample: the store record's per-detector entries match the
raw report's engine_results exactly; the combined decision is recorded verbatim
and equals the raw combined fields. Ensemble recomputation: the D0-frozen
aggregation formula is UNKNOWN, so recomputation is recorded NOT-RUN and the
check instead asserts verbatim storage traceable to the raw artifact.
"""
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)


def main(run_dir, store_dir, probe_set_path):
    report = {"check": "d2-scoring", "pass": False, "details": []}
    inv = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json")))["payload"]
    formula = inv["ensemble_rule"]["aggregation_formula"]
    probe = json.load(open(probe_set_path))["samples"]
    for sid in probe:
        record = json.load(open(os.path.join(store_dir, "records", sid + ".json")))
        raw = json.load(open(os.path.join(store_dir, "raw", sid + ".json")))
        if record.get("raw_report_id") != raw.get("id"):
            report["details"].append("%s: raw_report_id untraceable" % sid)
            continue
        want = {e["engine_name"]: {"score": e["score"], "verdict": e["verdict"],
                                   "details": e["details"]}
                for e in raw["engine_results"]}
        if record.get("per_detector_scores") != want:
            report["details"].append("%s: per-detector mismatch" % sid)
        overall = record.get("overall_verbatim", {})
        for field in ("overall_score", "overall_verdict", "engines_flagged", "engines_total"):
            if overall.get(field) != raw.get(field):
                report["details"].append("%s: %s not verbatim" % (sid, field))
        if "overall_recomputed" in record:
            report["details"].append("%s: claims recomputation" % sid)
    if formula == "UNKNOWN":
        report["details"].append("ensemble recomputation: NOT-RUN (formula UNKNOWN); "
                                 "verbatim storage asserted for %d samples" % len(probe))
        recompute_ok = True
    else:
        report["details"].append("STALE CHECK: formula now %s, recomputation branch unimplemented"
                                 % formula)
        recompute_ok = False
    fails = [d for d in report["details"] if not d.startswith("ensemble recomputation")]
    report["pass"] = not fails and recompute_ok
    json.dump(report, open(os.path.join(run_dir, "check-d2-scoring.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d2-scoring: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
