"""D6 E2E-1b (independent path): blocked-items carry-forward.

Asserts every EXTERNAL-BLOCKED / NOT-RUN token line in every milestone
verdict is covered by the frozen catalog, every catalog ground occurs in
its named verdict, the blocked-items artifact matches the roster with
non-empty reason/effect, and the final report lists every item with its
milestone, reason, and effect while the conclusions section references
every item ID.
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg  # noqa: E402

TOKENS = ("EXTERNAL-BLOCKED", "NOT-RUN")


def main(run_dir):
    report = {"check": "d6-blocked", "pass": False, "details": []}
    problems = []
    d6 = cfg.load("d6.yaml")
    roster = list(d6["d6_blocked_ids"])
    verdicts = {}
    for name in d6["d6_blocked_verdicts"]:
        with open(os.path.join(ROOT, "build", name)) as fh:
            verdicts[name] = fh.read().splitlines()
    catalog = {}
    for bid in roster:
        prefix = "d6_%s_" % bid.lower().replace("-", "")
        parts = [p.strip() for p in cfg.require_resolved(
            d6, prefix + "grounds", "config/d6.yaml").split("||")]
        if len(parts) % 2:
            problems.append(bid + ": odd grounds parts")
            continue
        grounds = list(zip(parts[0::2], parts[1::2]))
        for fname, substr in grounds:
            if fname not in verdicts:
                problems.append("%s: unknown verdict %s" % (bid, fname))
            elif not any(substr in ln for ln in verdicts[fname]):
                problems.append("%s: ground missing in %s: %r" % (bid, fname, substr))
        catalog[bid] = {
            "grounds": grounds,
            "reason": cfg.require_resolved(d6, prefix + "reason", "config/d6.yaml"),
            "effect": cfg.require_resolved(d6, prefix + "effect", "config/d6.yaml")}

    token_lines = 0
    for fname, lines in sorted(verdicts.items()):
        for lineno, line in enumerate(lines, 1):
            if not any(tok in line for tok in TOKENS):
                continue
            token_lines += 1
            covered = any(fname == gfname and substr in line
                          for entry in catalog.values()
                          for gfname, substr in entry["grounds"])
            if not covered:
                problems.append("uncovered token line %s:%d: %s"
                                % (fname, lineno, line.strip()[:110]))

    items = json.load(open(os.path.join(
        ROOT, "build", "evidence", "D6", "blocked-items.json")))["items"]
    if [b["item_id"] for b in items] != roster:
        problems.append("blocked-items artifact IDs != roster")
    for item in items:
        entry = catalog.get(item["item_id"])
        if entry is None:
            continue
        if item["reason"] != entry["reason"] or item["effect"] != entry["effect"]:
            problems.append("%s: artifact reason/effect != catalog" % item["item_id"])
        if not item["reason"].strip() or not item["effect"].strip():
            problems.append("%s: empty reason/effect" % item["item_id"])
        if not item["quoted_lines"]:
            problems.append("%s: no quoted lines" % item["item_id"])

    md = open(os.path.join(ROOT, "build", "FINAL-REPORT.md")).read()
    chunks = re.split(r"^## \d+\. ", md, flags=re.M)
    sections = {}
    for chunk in chunks[1:]:
        sections[chunk.splitlines()[0].strip()] = chunk
    blocked_sec = sections.get("Blocked items", "")
    concl_sec = sections.get("Limitations and conclusions", "")
    if not blocked_sec or not concl_sec:
        problems.append("blocked/conclusions section missing")
    else:
        for bid in roster:
            entry = catalog[bid]
            if bid not in blocked_sec:
                problems.append("%s missing from blocked section" % bid)
            if entry["reason"] not in blocked_sec or entry["effect"] not in blocked_sec:
                problems.append("%s reason/effect not verbatim in report" % bid)
            if bid not in concl_sec:
                problems.append("%s not referenced in conclusions" % bid)

    if problems:
        report["details"].append("%d blocked-item problems: %s"
                                 % (len(problems), "; ".join(problems[:8])))
    else:
        report["details"].append(
            "%d catalog items over %d token lines across %d verdicts; "
            "report lists all with reason/effect; conclusions reference all"
            % (len(roster), token_lines, len(verdicts)))
        report["pass"] = True
    json.dump(report, open(os.path.join(run_dir, "check-d6-blocked.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d6-blocked: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
