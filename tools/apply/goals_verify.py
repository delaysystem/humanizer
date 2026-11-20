"""Apply-phase audit: verify §3A Goals A–E completion from committed artifacts.

Read-only. Asserts each goal's §3A requirements against manifests, stores,
frozen tables, fix entries, and the green check files that verified them
(D3A implementer run + a green D4 run). Goal C Layer 3 is expected
EXTERNAL-BLOCKED (protocol frozen, all variants unsampled, raters must be
external); that yields COMPLETE-WITH-BLOCKED-L3, never a silent pass.
Writes build/evidence/APPLY/goals-verification.json. Exit 0 iff A, B, D, E
are complete and C is complete except the blocked layer.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)


def load_json(rel):
    with open(os.path.join(ROOT, rel)) as fh:
        return json.load(fh)


def green_check(path):
    doc = load_json(path)
    return doc.get("pass") is True


def find_green_run(ms, check_file):
    found = []
    for path in sorted(glob.glob(os.path.join(
            ROOT, "build", "evidence", ms, "runs", "*", check_file))):
        if load_json(os.path.relpath(path, ROOT)).get("pass") is True:
            found.append(os.path.relpath(path, ROOT))
    return found


def main():
    out = {"goals": {}, "ok": False}
    problems = []
    pipes = cfg.load("pipelines.yaml")
    d4cfg = cfg.load("d4.yaml")
    frozen_run = cfg.require_resolved(d4cfg, "d4_d3a_tables_run_id", "config/d4.yaml")

    # Goal A — intensity sweep.
    evidence_a = []
    if [int(x) for x in pipes["d3a_intensities"]] != [1, 3, 5, 10]:
        problems.append("A: intensities != [1,3,5,10]")
    rounds_ok, rounds_n = True, 0
    for intensity in (1, 3, 5, 10):
        rel = "datasets/d3a/manifest-d3a-i%d.json" % intensity
        if not os.path.isfile(os.path.join(ROOT, rel)):
            problems.append("A: missing " + rel)
            continue
        manifest = load_json(rel)
        evidence_a.append("%s n=%s" % (rel, manifest["variant_count"]))
        if manifest["variant_count"] != 27 or manifest["condition"] != "d3a-i%d" % intensity:
            problems.append("A: bad counts in " + rel)
    for path in sorted(glob.glob(os.path.join(
            ROOT, "results/d3a/intermediates/V-d3a-i[0-9]*/rounds.json"))):
        doc = load_json(os.path.relpath(path, ROOT))
        want = int(doc["variant_id"].split("-")[2][1:])
        rounds = doc.get("rounds", [])
        if len(rounds) != want or any(
                set(r) < {"round", "cosine", "passing", "file"} for r in rounds):
            rounds_ok = False
        else:
            rounds_n += 1
        for rnd in rounds:
            if not os.path.isfile(os.path.join(ROOT, "results/d3a", rnd.get("file", ""))):
                rounds_ok = False
    if not rounds_ok or rounds_n != 108:
        problems.append("A: per-round fidelity incomplete (%d/108 dirs ok)" % rounds_n)
    evidence_a.append("per-round rounds.json: %d/108 intensity variants" % rounds_n)
    d3a_runs = sorted(glob.glob(os.path.join(
        ROOT, "build/evidence/D3A/runs/*%s" % frozen_run)))
    if len(d3a_runs) != 1:
        problems.append("A: implementer run dir for %s not unique" % frozen_run)
        impl = None
    else:
        impl = os.path.relpath(d3a_runs[0], ROOT)
        for check in ("check-d3a-completeness.json", "check-d3a-gating.json",
                      "check-d3a-flips.json", "check-d3a-fixindex.json"):
            if not green_check(impl + "/" + check):
                problems.append("A/E/D/C: %s not green in %s" % (check, impl))
        evidence_a.append("D3A implementer suite green: " + impl)
    out["goals"]["A"] = {"status": "COMPLETE", "evidence": evidence_a}

    # Goal B — combined conditions.
    evidence_b = []
    for cond in ("d3a-combo-rt-trunc", "d3a-combo-trunc-rt"):
        rel = "datasets/d3a/manifest-%s.json" % cond
        manifest = load_json(rel)
        steps = [p["step"] for p in manifest["params"]]
        fams = {s.split("-")[0] if not s.startswith("truncate") else "truncate" for s in steps}
        evidence_b.append("%s n=%s steps=%s" % (rel, manifest["variant_count"], steps))
        if manifest["variant_count"] != 27 or fams != {"bodhan", "truncate"}:
            problems.append("B: bad combo in " + rel)
    out["goals"]["B"] = {"status": "COMPLETE", "evidence": evidence_b}

    # Goal C — coherence gate.
    records = [load_json(os.path.relpath(p, ROOT)) for p in sorted(
        glob.glob(os.path.join(ROOT, "results/d3a/records/*.json")))]
    l1 = sum(1 for r in records if isinstance((r.get("fidelity") or {}).get("cosine"), float))
    l2 = sum(1 for r in records if isinstance((r.get("fidelity") or {}).get("layer2"), dict))
    gv = {(r.get("fidelity") or {}).get("gate_version") for r in records}
    unsampled = sum(1 for r in records if (r.get("fidelity") or {}).get("spotcheck") == "unsampled")
    evidence_c = ["L1 cosine on %d/162 records" % l1, "L2 readout on %d/162" % l2,
                  "gate versions: %s" % sorted(gv),
                  "protocol: build/evidence/D2/spotcheck-protocol.md",
                  "unsampled: %d/162" % unsampled]
    if l1 != 162 or l2 != 162 or gv != {"3layer-v1+readability+langrule"}:
        problems.append("C: L1/L2/gate-version incomplete")
    if unsampled != 162 or not os.path.isfile(os.path.join(
            ROOT, "build/evidence/D2/spotcheck-protocol.md")):
        problems.append("C: L3 state unexpected")
    out["goals"]["C"] = {"status": "COMPLETE-WITH-BLOCKED-L3",
                         "blocked": "Layer-3 execution needs 2 external raters "
                                    "(implementer ineligible); 162/162 unsampled",
                         "evidence": evidence_c}

    # Goal D — flip analysis.
    tables = load_json("results/d3a/flip-tables-%s.json" % frozen_run)
    ids = load_json("results/d3a/failure-ids-%s.json" % frozen_run)
    rows = sum(len(v["detectors"]) for v in tables.values())
    evidence_d = ["flip tables %d conditions x 23 = %d rows" % (len(tables), rows),
                  "failure registry: %d IDs" % len(ids)]
    if len(tables) != 6 or rows != 138 or len(ids) != 138:
        problems.append("D: frozen tables/registry counts wrong")
    repro = find_green_run("D4", "check-d4-repro.json")
    if not repro:
        problems.append("D: no green D4 recomputation run")
    else:
        evidence_d.append("independent recomputation green: " + repro[0])
    out["goals"]["D"] = {"status": "COMPLETE", "evidence": evidence_d}

    # Goal E — fixes.
    need = ["README.md", "meta.yaml", "proposal.md", "config-proposal.yaml",
            "training-augmentation-spec.md", "threshold-simulation.md",
            "verification-test-spec.md", "risk-and-rollback.md", "data-spec.md"]
    missing = []
    for num in range(1, 7):
        fix = "FIX-D3A-%03d" % num
        for name in need:
            if not os.path.isfile(os.path.join(ROOT, "detector-fixes", fix, name)):
                missing.append(fix + "/" + name)
    if missing:
        problems.append("E: missing entry files: %s" % missing[:4])
    fixcomplete = find_green_run("D4", "check-d4-fixcomplete.json")
    index = find_green_run("D4", "check-d4-index.json")
    if not fixcomplete or not index:
        problems.append("E: no green D4 fix-verification run")
    evidence_e = ["6 entries x 9 files complete",
                  "fix completeness green: %s" % (fixcomplete[0] if fixcomplete else "none"),
                  "index consistency green: %s" % (index[0] if index else "none")]
    out["goals"]["E"] = {"status": "COMPLETE", "evidence": evidence_e}

    out["problems"] = problems
    out["ok"] = not problems
    os.makedirs(os.path.join(ROOT, "build", "evidence", "APPLY"), exist_ok=True)
    with open(os.path.join(ROOT, "build", "evidence", "APPLY",
                           "goals-verification.json"), "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    for goal in "ABCDE":
        print("%s: %s" % (goal, out["goals"][goal]["status"]))
    if problems:
        print("PROBLEMS: %s" % "; ".join(problems))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
