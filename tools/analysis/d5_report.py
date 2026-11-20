"""D5: assemble the frozen drift report from one suite run's comparisons +
the cleanroom diff. Run once (implementer inputs); deterministic given the
same inputs (run-ids cited as evidence links, no timestamps).

Usage: d5_report.py --run-dir <implementer run> --cleanroom-diff <json> --out build/evidence/D5
"""
import argparse
import json
import os
import sys


def main(args):
    drift_stats = json.load(open(os.path.join(args.run_dir, "drift-stats.json")))
    drift_cmp = json.load(open(os.path.join(args.run_dir, "drift-compare.json")))
    rescore = json.load(open(os.path.join(args.run_dir, "check-d5-rescore.json")))
    gate = json.load(open(os.path.join(args.run_dir, "check-d5-gate.json")))
    scan = json.load(open(os.path.join(args.run_dir, "scan-report.json")))
    crdiff = json.load(open(args.cleanroom_diff))
    report = {
        "d5_drift_report": True,
        "source_run": os.path.basename(args.run_dir),
        "regen": {"stats": drift_stats, "per_sample": drift_cmp["run_samples"],
                  "truncate_byte_issues": drift_cmp["truncate_byte_issues"]},
        "rescoring": {"pass": rescore["pass"], "details": rescore["details"]},
        "cleanroom": crdiff,
        "gate": {"pass": gate["pass"], "details": gate["details"],
                 "workers": scan["workers"],
                 "allowlist_ids": scan["allowlist_ids"]},
    }
    with open(os.path.join(args.out, "drift-report.json"), "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    with open(os.path.join(args.out, "drift-report.md"), "w") as fh:
        fh.write("# D5 drift report (generated from run %s)\n\n"
                 % os.path.basename(args.run_dir))
        fh.write("## Regen (E2E-1b): %d samples, fidelity mean %.4f min %.4f, "
                 "score-delta mean %.2f max %.2f\n\n" % (
                     drift_stats["n"], drift_stats["fidelity_mean"],
                     drift_stats["fidelity_min"], drift_stats["delta_mean"],
                     drift_stats["delta_max"]))
        fh.write("Truncate byte-identity issues: %s.\n\n"
                 % (drift_cmp["truncate_byte_issues"] or "none"))
        fh.write("## Rescoring (E2E-3): %s — %s\n\n" % (
            "PASS" if rescore["pass"] else "FAIL", "; ".join(rescore["details"])))
        fh.write("## Cleanroom: %d scores compared, %d mismatches (worst d=%.4f); "
                 "fixes differing: %d; D4 report identical: %s.\n\n" % (
                     crdiff["scores"]["compared"], len(crdiff["scores"]["mismatches"]),
                     crdiff["scores"]["worst_delta"], len(crdiff["fixes_tree"]["differing"]),
                     crdiff["d4_report_identical"]))
        fh.write("## Gate (E2E-4): %s — %s\n" % (
            "PASS" if gate["pass"] else "FAIL", "; ".join(gate["details"])))
    print("drift report written (%s)" % ("clean" if rescore["pass"] and gate["pass"] else "see details"))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="d5_report")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--cleanroom-diff", required=True)
    parser.add_argument("--out", required=True)
    sys.exit(main(parser.parse_args()))
