"""D0 E2E-2 (independent path): distinct per-engine score artifacts equal the frozen inventory.

Sloptotal exposes one scoring endpoint returning all engines in a single
report (observed D0 Probe 1/2: engines are aggregate-visible, not individually
callable), so the suite splits one raw report into per-engine files and this
reader counts them against the frozen name set. Expected count is derived from
the frozen inventory file itself, never a literal.
"""
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)


def main(run_dir):
    report = {"check": "d0-inventory", "pass": False, "details": []}
    inv = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json")))["payload"]["detectors"]
    expected = sorted(e["key"] for e in inv)
    scores_dir = os.path.join(run_dir, "scores")
    if not os.path.isdir(scores_dir):
        report["details"].append("scores dir missing (scoring never completed)")
        report["pass"] = False
        json.dump(report, open(os.path.join(run_dir, "check-d0-inventory.json"), "w"), indent=2)
        print("FAIL d0-inventory: " + "; ".join(report["details"]))
        return 1
    actual = sorted(f[:-5] for f in os.listdir(scores_dir) if f.endswith(".json"))
    if len(actual) != len(set(actual)):
        report["details"].append("duplicate score artifacts")
    if actual != expected:
        report["details"].append("count actual=%d expected=%d" % (len(actual), len(expected)))
        report["details"].append("missing=%s extra=%s"
                                 % (sorted(set(expected) - set(actual)),
                                    sorted(set(actual) - set(expected))))
    else:
        report["details"].append("count=%d; name set equals frozen inventory"
                                 % len(actual))
    report["pass"] = not [d for d in report["details"] if not d.startswith("count=")]
    json.dump(report, open(os.path.join(run_dir, "check-d0-inventory.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d0-inventory: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
