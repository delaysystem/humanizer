"""D4 E2E-4 (independent path): status honesty — PROPOSED_NOT_APPLIED appears
in every FIX entry; the stems applied|implemented|fixed|resolved|shipped
(case-insensitive, after removing the literal PROPOSED_NOT_APPLIED) yield
zero hits. Raw grep output is preserved as evidence.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)

STEMS = re.compile(r"applied|implemented|fixed|resolved|shipped", re.IGNORECASE)
LITERAL = re.compile(r"PROPOSED_NOT_APPLIED", re.IGNORECASE)


def main(run_dir, fixes_dir):
    report = {"check": "d4-honesty", "pass": False, "details": []}
    grep_lines = []
    entries = sorted(d for d in os.listdir(fixes_dir)
                     if os.path.isdir(os.path.join(fixes_dir, d)) and d.startswith("FIX-"))
    if not entries:
        report["details"].append("no FIX entries found")
    for fix_id in entries:
        found_literal = False
        for path in sorted(glob.glob(os.path.join(fixes_dir, fix_id, "*"))):
            if not os.path.isfile(path):
                continue
            text = open(path, errors="replace").read()
            if "PROPOSED_NOT_APPLIED" in text:
                found_literal = True
            stripped = LITERAL.sub("", text)
            for i, line in enumerate(stripped.split("\n"), 1):
                for match in STEMS.finditer(line):
                    grep_lines.append("%s:%d:%s" % (
                        os.path.join(fix_id, os.path.basename(path)), i,
                        line.strip()[:120]))
        if not found_literal:
            report["details"].append("%s: PROPOSED_NOT_APPLIED absent" % fix_id)
    with open(os.path.join(run_dir, "honesty-grep.txt"), "w") as fh:
        fh.write("\n".join(grep_lines) + ("\n" if grep_lines else ""))
    if grep_lines:
        report["details"].append("%d banned-stem hits (see honesty-grep.txt)" % len(grep_lines))
    if not report["details"]:
        report["details"].append("%d entries carry PROPOSED_NOT_APPLIED; zero banned stems"
                                 % len(entries))
    report["pass"] = not [d for d in report["details"] if "zero banned stems" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d4-honesty.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d4-honesty: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
