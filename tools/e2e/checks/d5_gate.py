"""D5 E2E-4 (independent path): no-humanizer / public-exposure gate.

(a) Route handlers + exported evasion functions in harness code: zero hits.
    CLI entry points are inventoried; plan-mandated batch CLIs under the
    harness roots are allowed with a recorded reason (same precedent as the
    plan's tools/e2e/ exclusion: batch evaluation runners that serve no
    requests are not user evasion surfaces); anything else fails.
(b) Evasion words + §3C recommendation phrases in user-facing docs: zero hits.
Workers: src/index.ts must still be the undeployed queue-template scaffold
    (mechanical tripwire); the §3B endpoints were never deployed here, so
    I-1/I-2/I-3 are recorded NOT-RUN with reason. If the scaffold ever
    changes, this check fails demanding full I-1/I-2/I-3 implementation.
Allowlist: every data file under the known suite stores resolves to an
    artifact ID derived from manifests + pipeline defs (by ID, not filename);
    build/evidence top dirs are limited to the milestone spine.
Manual checklist: review-checklist.md must cover every scanned doc.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg
import pipeline as pipe

# Plan-mandated batch runners: no request serving, datasets only. Same
# precedent as the plan's explicit tools/e2e/ exclusion.
HARNESS_CLI_ROOTS = ("tools/harness", "tools/analysis")
STORE_DIRS = ("results/d2", "results/d2-deadprobe", "results/d3", "results/d3-deadprobe",
              "results/d3-replaceprobe", "results/d3a", "results/d3a-originals")
RUN_FILE_RES = [
    re.compile(r"^attempts-.*\.(log|json)$"), re.compile(r"^blocked-.*\.json$"),
    re.compile(r"^(bodhan-)?audit-.*\.jsonl?$"), re.compile(r"^excluded-.*\.json$"),
    re.compile(r"^(flip-tables|failure-ids)-.*\.json$"), re.compile(r"^check-.*\.json$"),
    re.compile(r"^(manifest|transcript|console|honesty-grep|variant-id-list|matched-join|"
               r"near-dup-flags|spread-table|fidelity-observed|score-report|d3-language-audit|"
               r"originals-probe-set|drift-(sample|compare|stats)|rescore-blocked|noedit-.*|"
               r"fixes-snapshot).*(\.json|\.log|\.txt)$"),
    re.compile(r"^rep\d+\.json$"), re.compile(r"^round\d+\.txt$"),
    re.compile(r"^rounds\.json$"), re.compile(r"^container-logs\.txt$"),
    re.compile(r"^baseline-live\.json$"),
]
SPINE_DIRS = {"D0", "D1", "D2", "D3", "D3A", "D4", "D5", "D6"}
SCAFFOLD_MARKERS = ("Welcome to Cloudflare Workers!", "env.MY_QUEUE.send",
                    "Sent message to the queue")


def walk(root, exclude_dirs, extensions):
    hits = []
    for base, dirs, files in os.walk(root):
        # Dot-dirs are tool-owned caches (.models weights, .venv, .git), never repo docs.
        dirs[:] = sorted(d for d in dirs if d not in exclude_dirs and not d.startswith("."))
        for name in sorted(files):
            if os.path.splitext(name)[1] in extensions:
                hits.append(os.path.join(base, name))
    return sorted(hits)


def main(run_dir):
    report = {"check": "d5-gate", "pass": False, "details": []}
    d5 = cfg.load("d5.yaml")
    route_res = [re.compile(p, re.IGNORECASE) for p in d5["d5_gate_route_patterns"]]
    export_res = [re.compile(p) for p in d5["d5_gate_export_patterns"]]
    cli_res = [re.compile(p) for p in d5["d5_gate_cli_patterns"]]
    word_res = [re.compile(w, re.IGNORECASE) for w in d5["d5_gate_evasion_words"]]
    phrase_res = [re.compile(re.escape(p), re.IGNORECASE)
                  for p in d5["d5_gate_recommendation_phrases"]]
    exclude_dirs = set(d5["d5_gate_exclude_dirs"])
    exclude_files = set(d5["d5_gate_exclude_files"])
    findings = {"route_hits": [], "export_hits": [], "cli_inventory": [], "doc_hits": []}

    for code_root in d5["d5_gate_code_paths"]:
        for path in walk(os.path.join(ROOT, code_root), exclude_dirs, (".py",)):
            rel = os.path.relpath(path, ROOT)
            text = open(path, errors="replace").read()
            for rx in route_res + export_res:
                for i, line in enumerate(text.split("\n"), 1):
                    if rx.search(line):
                        findings["route_hits" if rx in route_res else "export_hits"].append(
                            "%s:%d:%s" % (rel, i, line.strip()[:100]))
            if any(rx.search(text) for rx in cli_res) and "__main__" in text:
                allowed = rel.startswith(HARNESS_CLI_ROOTS)
                findings["cli_inventory"].append(
                    {"file": rel, "disposition": "harness-batch-allowed" if allowed
                     else "FORBIDDEN-CLI"})
                if not allowed:
                    findings["route_hits"].append(rel + ": non-harness CLI entry point")

    scanned_docs = []
    for docs_root in d5["d5_gate_docs_roots"]:
        for path in walk(os.path.join(ROOT, docs_root), exclude_dirs, (".md",)):
            rel = os.path.relpath(path, ROOT)
            if rel in exclude_files:
                continue
            scanned_docs.append(rel)
            text = open(path, errors="replace").read()
            for rx in word_res + phrase_res:
                for i, line in enumerate(text.split("\n"), 1):
                    if rx.search(line):
                        findings["doc_hits"].append("%s:%d:%s" % (rel, i, line.strip()[:100]))

    exclusions_quoted = {}
    for rel in sorted(exclude_files):
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        text = open(path, errors="replace").read()
        quoted = []
        for rx in word_res + phrase_res:
            for i, line in enumerate(text.split("\n"), 1):
                if rx.search(line):
                    quoted.append("%d:%s" % (i, line.strip()[:120]))
        exclusions_quoted[rel] = quoted

    worker_path = os.path.join(ROOT, "src", "index.ts")
    worker_text = open(worker_path, errors="replace").read() if os.path.isfile(worker_path) else ""
    scaffold = all(m in worker_text for m in SCAFFOLD_MARKERS)
    workers_note = ("no Workers deployment exists in evidence; src/index.ts is the "
                    "undeployed queue-template scaffold; §3B I-1/I-2/I-3 NOT-RUN "
                    "(nothing to test)")
    if not scaffold:
        findings["route_hits"].append("src/index.ts scaffold changed: implement I-1/I-2/I-3")

    manifest = json.load(open(os.path.join(ROOT, "datasets", "v1", "manifest.json")))
    pipes = cfg.load("pipelines.yaml")
    allowed_ids = {s["sample_id"] for s in manifest["samples"]}
    for key in pipes:
        if key.startswith("pipeline_") and key.endswith("_steps"):
            pipe_id = key[len("pipeline_"):-len("_steps")]
            sel = cfg.require_resolved(pipes, "pipeline_%s_samples" % pipe_id,
                                       "config/pipelines.yaml")
            for sid in pipe._select(manifest, sel):
                allowed_ids.add("V-%s-%s" % (pipe_id, sid))
    allow_issues = []
    for store in STORE_DIRS:
        for base, _dirs, files in os.walk(os.path.join(ROOT, store)):
            for name in sorted(files):
                rel = os.path.relpath(os.path.join(base, name), ROOT)
                stem = name
                stripped = True
                while stripped:
                    stripped = False
                    for suffix in (".meta.json", ".json", ".txt"):
                        if stem.endswith(suffix):
                            stem = stem[: -len(suffix)]
                            stripped = True
                if stem in allowed_ids:
                    continue
                if any(rx.match(name) for rx in RUN_FILE_RES):
                    continue
                allow_issues.append(rel)
    ev_root = os.path.join(ROOT, "build", "evidence")
    for entry in sorted(os.listdir(ev_root)):
        if os.path.isdir(os.path.join(ev_root, entry)) and entry not in SPINE_DIRS:
            allow_issues.append("build/evidence/%s: outside milestone spine" % entry)

    checklist_path = os.path.join(ROOT, "build", "evidence", "D5", "review-checklist.md")
    checklist_ok = True
    if not os.path.isfile(checklist_path):
        checklist_ok = False
        findings["doc_hits"].append("review-checklist.md missing")
    else:
        checklist = open(checklist_path, errors="replace").read()
        if "reviewed_by:" not in checklist or "review_date:" not in checklist:
            checklist_ok = False
            findings["doc_hits"].append("review-checklist.md lacks reviewer/date attestation")
        for doc in scanned_docs:
            if ("- [x] `%s`" % doc) not in checklist:
                checklist_ok = False
                findings["doc_hits"].append("review-checklist.md does not cover %s" % doc)

    scan = {"patterns": {"routes": d5["d5_gate_route_patterns"],
                         "exports": d5["d5_gate_export_patterns"],
                         "cli": d5["d5_gate_cli_patterns"],
                         "evasion_words": d5["d5_gate_evasion_words"],
                         "recommendation_phrases": d5["d5_gate_recommendation_phrases"]},
            "code_paths": d5["d5_gate_code_paths"], "docs_roots": d5["d5_gate_docs_roots"],
            "exclude_dirs": sorted(exclude_dirs), "exclude_files": sorted(exclude_files),
            "exclusions_quoted": exclusions_quoted, "findings": findings,
            "workers": workers_note, "scaffold_markers_present": scaffold,
            "allowlist_ids": len(allowed_ids), "allow_issues": allow_issues,
            "scanned_docs": scanned_docs, "checklist_ok": checklist_ok}
    json.dump(scan, open(os.path.join(run_dir, "scan-report.json"), "w"), indent=2, sort_keys=True)
    with open(os.path.join(run_dir, "scan-report.md"), "w") as fh:
        fh.write("# D5 gate scan report (generated)\n\n")
        fh.write("Workers: %s.\n\n" % workers_note)
        fh.write("Findings: %s.\n\n" % ("ZERO (a)/(b) hits" if not (
            findings["route_hits"] or findings["export_hits"] or findings["doc_hits"])
            else "FAIL — see findings"))
        fh.write("CLI inventory (%d, all harness-batch-allowed unless flagged):\n\n"
                 % len(findings["cli_inventory"]))
        for item in findings["cli_inventory"]:
            fh.write("- %s — %s\n" % (item["file"], item["disposition"]))
        fh.write("\nAllowlist: %d artifact IDs; issues: %s.\n" % (
            len(allowed_ids), allow_issues if allow_issues else "none"))
    problems = (findings["route_hits"] + findings["export_hits"] + findings["doc_hits"]
                + allow_issues)
    if problems:
        report["details"].append("%d gate problems: %s" % (len(problems), "; ".join(problems[:8])))
    else:
        report["details"].append("zero (a)/(b) hits; %d CLIs inventoried (harness-batch); "
                                 "Workers scaffold, I-1/I-2/I-3 NOT-RUN; allowlist %d IDs clean; "
                                 "checklist covers %d docs"
                                 % (len(findings["cli_inventory"]), len(allowed_ids),
                                    len(scanned_docs)))
    report["pass"] = not problems
    json.dump(report, open(os.path.join(run_dir, "check-d5-gate.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d5-gate: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
