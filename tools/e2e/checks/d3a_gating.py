"""D3A E2E-7 (independent path): three-layer gating — passing equals
(cosine >= threshold AND no language mismatch); exclusion lists exact;
records carry the D3A gate version + readability + language readout.
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


def main(run_dir, store_dir, run_id):
    report = {"check": "d3a-gating", "pass": False, "details": []}
    fid = cfg.load("fidelity.yaml")
    threshold = cfg.require_resolved(fid, "fidelity_threshold", "config/fidelity.yaml")
    version = cfg.require_resolved(fid, "gate_version_d3a", "config/fidelity.yaml")
    failing, passing = [], []
    for path in sorted(glob.glob(os.path.join(store_dir, "records", "*.json"))):
        record = json.load(open(path))
        fidel = record.get("fidelity") or {}
        sid = record.get("sample_id")
        for field in ("cosine", "fidelity_passing", "gate_version", "language", "layer2"):
            if field not in fidel:
                report["details"].append("%s: fidelity.%s missing" % (sid, field))
        if fidel.get("gate_version") != version:
            report["details"].append("%s: gate version %s" % (sid, fidel.get("gate_version")))
        if "readability" not in (fidel.get("layer2") or {}):
            report["details"].append("%s: readability missing" % sid)
        expect = fidel.get("cosine", -1) >= threshold and not (fidel.get("language") or {}).get("mismatch")
        if bool(fidel.get("fidelity_passing")) != expect:
            report["details"].append("%s: passing=%s vs rule %s"
                                     % (sid, fidel.get("fidelity_passing"), expect))
        (passing if expect else failing).append(sid)
    listed = set()
    for pipe in cfg.load("pipelines.yaml")["d3a_pipelines"]:
        excl = json.load(open(os.path.join(store_dir, "excluded-%s-%s.json" % (run_id, pipe))))
        listed.update(excl.get("degraded_variant_ids", []))
    if set(failing) != listed:
        report["details"].append("exclusion list != failing set")
    if not report["details"]:
        report["details"].append("%d passing, %d degraded; rule + version + readout exact"
                                 % (len(passing), len(failing)))
    report["pass"] = not [d for d in report["details"] if "exact" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3a-gating.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3a-gating: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
