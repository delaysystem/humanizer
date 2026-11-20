"""D2 E2E-2 (independent path): fidelity gate honors the pre-registered anchors.

Runs the real gate (fresh model load) on the frozen anchor pairs only and
asserts high passes + degraded fails. Also re-derives the frozen threshold
rule from the observed scores and asserts config matches (guards hand-edits).
The anchors-were-first claim is process evidence (anchors frozen before the
model was downloaded — see session order + D2 verdict), asserted here by the
anchors file carrying pre-registered expectations.
"""
import json
import math
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg
import fidelity


def main(run_dir):
    report = {"check": "d2-fidelity", "pass": False, "details": []}
    frozen = json.load(open(os.path.join(ROOT, "build/evidence/D2/fidelity-anchors.json")))
    if "threshold_rule" not in frozen:
        report["details"].append("no frozen threshold rule")
    model = fidelity.load_model()
    observed = {}
    for anchor in frozen["anchors"]:
        original = open(os.path.join(ROOT, anchor["original_ref"])).read()
        result = fidelity.gate(original, anchor["variant"], model=model)
        got = "pass" if result["fidelity_passing"] else "fail"
        observed[anchor["id"]] = result["cosine"]
        if got != anchor["expected"]:
            report["details"].append("%s: expected %s, gate says %s (cosine %s)"
                                     % (anchor["id"], anchor["expected"], got, result["cosine"]))
    hi = observed.get("anchor-high-1")
    lo = observed.get("anchor-low-1")
    if hi is not None and lo is not None:
        if hi - lo < 0.2:
            report["details"].append("anchor gap %.4f below frozen 0.2 adequacy bar" % (hi - lo))
        derived = math.floor(((hi + lo) / 2) * 20) / 20
        configured = cfg.require_resolved(cfg.load("fidelity.yaml"), "fidelity_threshold",
                                          "config/fidelity.yaml")
        if abs(derived - configured) > 1e-9:
            report["details"].append("config threshold %s != rule-derived %s" % (configured, derived))
        else:
            report["details"].append("anchors honored (high %.4f / low %.4f); threshold %.2f matches rule"
                                     % (hi, lo, configured))
    json.dump({"observed": observed}, open(os.path.join(run_dir, "fidelity-observed.json"), "w"),
              indent=2)
    report["pass"] = not [d for d in report["details"] if not d.startswith("anchors honored")]
    json.dump(report, open(os.path.join(run_dir, "check-d2-fidelity.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d2-fidelity: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
