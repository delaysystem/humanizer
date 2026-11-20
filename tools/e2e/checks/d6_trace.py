"""D6 E2E-3 (independent path): report traceability (mechanical).

Extracts every trace tag from the final report, joins tags to the
traceability table by ID, runs each row's recomputation command as a
separate process, and asserts all rows match. Also enforces the
digit-convention: outside fenced blocks, headings, quote lines, code
spans, URLs, and tags, no standalone number may appear — every
digit-written report value carries a tag. Writes the verified table
(traceability-verified.json: the plan's recomputed_value +
match_within_tolerance columns) plus check-d6-trace.json.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg  # noqa: E402

TAG_RE = re.compile(r"\[([^\]]+)\]\(#num-([A-Za-z0-9_.-]+)\)")
CODE_RE = re.compile(r"`[^`]*`")
URL_RE = re.compile(r"https?://\S+")
STANDALONE_RE = re.compile(r"(?<![A-Za-z0-9_.\-/§(:])\d+(\.\d+)?%?(?![A-Za-z0-9_])")
REQUIRED_FIELDS = ("number_id", "value_as_reported", "artifact_id",
                   "recomputation", "tolerance_name", "tolerance_value")


def main(run_dir):
    report = {"check": "d6-trace", "pass": False, "details": []}
    trace = json.load(open(os.path.join(
        ROOT, "build", "evidence", "D6", "traceability.json")))["numbers"]
    rows = {}
    for row in trace:
        missing = [f for f in REQUIRED_FIELDS if f not in row]
        if missing:
            report["details"].append("row missing fields %s" % missing)
            return finish(report, run_dir, 1)
        if row["number_id"] in rows:
            report["details"].append("duplicate number_id " + row["number_id"])
            return finish(report, run_dir, 1)
        rows[row["number_id"]] = row
    lines = open(os.path.join(ROOT, "build", "FINAL-REPORT.md")).read().splitlines()
    cited = {}
    for lineno, line in enumerate(lines, 1):
        for value, nid in TAG_RE.findall(line):
            cited.setdefault(nid, []).append((lineno, value))
    problems = []
    for nid, occurrences in sorted(cited.items()):
        if nid not in rows:
            problems.append("tag without trace row: %s (line %d)" % (nid, occurrences[0][0]))
            continue
        for lineno, value in occurrences:
            if value != rows[nid]["value_as_reported"]:
                problems.append("tag value %r != row %r for %s (line %d)"
                                % (value, rows[nid]["value_as_reported"], nid, lineno))
    for nid in sorted(rows):
        if nid not in cited:
            problems.append("trace row never cited in report: " + nid)
    in_fence = False
    for lineno, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line.startswith("#") or line.lstrip().startswith(">"):
            continue
        scrubbed = URL_RE.sub("", CODE_RE.sub("", TAG_RE.sub("", line)))
        for match in STANDALONE_RE.finditer(scrubbed):
            problems.append("untagged number %r (line %d)" % (match.group(0), lineno))
    if problems:
        report["details"].append("%d tag/scan problems: %s"
                                 % (len(problems), "; ".join(problems[:10])))
        return finish(report, run_dir, 1)
    tols = cfg.load("tolerances.yaml")
    live_pct_tol = cfg.require_resolved(tols, "percentage_recompute_rounding",
                                        "config/tolerances.yaml")
    verified, mismatches = [], []
    for row in trace:
        nid = row["number_id"]
        if row["tolerance_name"] == "percentage_recompute_rounding":
            if row["tolerance_value"] != live_pct_tol:
                mismatches.append("%s: stale tolerance %r" % (nid, row["tolerance_value"]))
                continue
        elif row["tolerance_name"] != "exact" or row["tolerance_value"] != 0:
            mismatches.append("%s: unknown tolerance %r" % (nid, row["tolerance_name"]))
            continue
        try:
            done = subprocess.run(row["recomputation"].split(), cwd=ROOT,
                                  capture_output=True, text=True, timeout=600)
        except Exception as exc:  # noqa: BLE001 — loud, counted, never swallowed
            mismatches.append("%s: recomputation error %s" % (nid, exc))
            continue
        if done.returncode != 0:
            mismatches.append("%s: recomputation exit %d: %s"
                              % (nid, done.returncode, done.stderr.strip()[:120]))
            continue
        recomputed = done.stdout.strip()
        if row["tolerance_name"] == "percentage_recompute_rounding":
            try:
                match = abs(float(recomputed) - float(row["value_as_reported"])) \
                    <= row["tolerance_value"]
            except ValueError:
                match = False
        else:
            match = recomputed == row["value_as_reported"]
        verified.append({
            "number_id": nid, "value_as_reported": row["value_as_reported"],
            "artifact_id": row["artifact_id"], "recomputation": row["recomputation"],
            "recomputed_value": recomputed,
            "match_within_tolerance": "yes" if match else "no"})
        if not match:
            mismatches.append("%s: reported %r recomputed %r"
                              % (nid, row["value_as_reported"], recomputed))
    json.dump({"numbers": verified},
              open(os.path.join(run_dir, "traceability-verified.json"), "w"),
              indent=2, sort_keys=True)
    if mismatches:
        report["details"].append("%d mismatches of %d: %s"
                                 % (len(mismatches), len(trace),
                                    "; ".join(mismatches[:10])))
        return finish(report, run_dir, 1)
    report["details"].append(
        "%d rows cited, scanned clean, all recomputations match" % len(trace))
    return finish(report, run_dir, 0)


def finish(report, run_dir, code):
    report["pass"] = code == 0
    json.dump(report, open(os.path.join(run_dir, "check-d6-trace.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d6-trace: " + "; ".join(report["details"]))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
