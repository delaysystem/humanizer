"""D4 E2E-2 (independent path): recompute the significant-mode set from the
frozen stores + config with separate code, and assert every significant mode
has exactly one FIX-D4-* entry whose failure ID resolves and whose evidence
links exist (no missing modes, no extra entries).
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
sys.path.insert(0, os.path.join(ROOT, "tools", "e2e", "checks"))
import config as cfg
from d4_repro import _wilson

REQUIRED_FILES = ["README.md", "meta.yaml", "proposal.md", "config-proposal.yaml",
                  "training-augmentation-spec.md", "threshold-simulation.md",
                  "verification-test-spec.md", "risk-and-rollback.md", "data-spec.md"]


def read_index_yaml(path):
    """Minimal reader for the fixed INDEX.yaml schema (no dependency)."""
    fixes, current = [], None
    for line in open(path):
        if line.startswith("  - fix_id: "):
            current = {"fix_id": line.split(": ", 1)[1].strip()}
            fixes.append(current)
        elif line.startswith("    ") and current is not None and ": " in line:
            key, val = line.strip().split(": ", 1)
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip() for v in val[1:-1].split(",") if v.strip()]
            current[key] = val
    return fixes


def main(run_dir, d3_store, d3a_store, orig_store, d3a_ids, d3_ids, fixes_dir):
    report = {"check": "d4-fixcomplete", "pass": False, "details": []}
    analysis = cfg.load("analysis.yaml")
    ai = set(analysis["flip_verdict_map_ai"])
    human = set(analysis["flip_verdict_map_human"])
    min_n = cfg.require_resolved(analysis, "analysis_minimum_n", "config/analysis.yaml")
    min_rate = cfg.require_resolved(analysis, "analysis_minimum_rate", "config/analysis.yaml")
    level = cfg.require_resolved(analysis, "analysis_ci_level", "config/analysis.yaml")
    bound = cfg.require_resolved(analysis, "analysis_ci_lower_bound",
                                 "config/analysis.yaml")
    inv = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json")))["payload"]["detectors"]
    name_of = {d["key"]: d["name"] for d in inv}
    code_of = {d["name"]: d["code"] for d in inv}
    originals = {}
    for path in glob.glob(os.path.join(orig_store, "records", "*.json")):
        rec = json.load(open(path))
        originals[rec["sample_id"]] = rec["per_detector_scores"]
    expected = {}
    for store_dir in (d3_store, d3a_store):
        grouped = {}
        for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
            rec = json.load(open(path))
            grouped.setdefault(rec["condition_id"], []).append(rec)
        for condition in sorted(grouped):
            passing = [v for v in grouped[condition] if v["fidelity"]["fidelity_passing"]]
            n = len(passing)
            for det in inv:
                name = det["name"]
                flips = sum(1 for v in passing
                            if originals[v["original_id"]][name]["verdict"] in ai
                            and v["per_detector_scores"][name]["verdict"] in human)
                lo, _hi = _wilson(flips, n, level)
                if n >= min_n and flips / n >= min_rate and lo >= bound:
                    fid = "FAIL-%s-%s-001" % (code_of[name], condition)
                    expected[(condition, name)] = fid
    rows = [f for f in read_index_yaml(os.path.join(fixes_dir, "INDEX.yaml"))
            if f["fix_id"].startswith("FIX-D4-")]
    have = {}
    for row in rows:
        dets = row["target_detector_ids"]
        conds = row["condition_ids"]
        fids = row["failure_ids"]
        if len(dets) != 1 or len(conds) != 1 or len(fids) != 1:
            report["details"].append("%s: per-mode row must be singletons" % row["fix_id"])
            continue
        have[(conds[0], name_of[dets[0]])] = (row["fix_id"], fids[0])
    for mode in sorted(expected):
        if mode not in have:
            report["details"].append("significant mode without entry: %s %s" % mode)
    for mode in sorted(have):
        if mode not in expected:
            report["details"].append("entry without significant mode: %s" % have[mode][0])
    reg_d3a = json.load(open(d3a_ids))
    reg_d3 = json.load(open(d3_ids))
    for mode in sorted(set(expected) & set(have)):
        fix_id, fid = have[mode]
        if expected[mode] != fid:
            report["details"].append("%s: failure ID %s != %s" % (fix_id, fid, expected[mode]))
        reg = reg_d3a if mode[0].startswith("d3a-") else reg_d3
        if fid not in reg:
            report["details"].append("%s: %s unresolvable" % (fix_id, fid))
        fix_dir = os.path.join(fixes_dir, fix_id)
        for fname in REQUIRED_FILES:
            if not os.path.isfile(os.path.join(fix_dir, fname)):
                report["details"].append("%s: missing %s" % (fix_id, fname))
        row = [r for r in rows if r["fix_id"] == fix_id][0]
        for path in row["evidence_artifact_ids"]:
            full = os.path.join(ROOT, path)
            if "*" in path:
                found = glob.glob(full)
            else:
                found = [full] if os.path.isfile(full) else []
            if not found:
                report["details"].append("%s: evidence missing %s" % (fix_id, path))
    if not report["details"]:
        report["details"].append("%d significant modes, all with resolving entries + evidence"
                                 % len(expected))
    report["pass"] = not [d for d in report["details"] if "all with resolving" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d4-fixcomplete.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d4-fixcomplete: "
          + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4],
                  sys.argv[5], sys.argv[6], sys.argv[7]))
