"""D0 E2E-5 (independent path): anti-hardcode scan of the milestone diff (P2).

Scope: D0-owned code dirs (tools/). config/ is the allowed source of environment
facts; build/ holds evidence records, not logic; src/ is owned by the §3B
Worker milestone (untouched in D0) and is covered by that milestone's scan.
Fails on:
  1. URL/host literals (scheme://...) — these belong in config/*.yaml.
  2. Secret-shaped assignments (keyword = quoted value, excluding $VAR and
     <placeholder> references).
  3. Test-detection identifiers (branches that change behavior under test).
  4. Numeric tuning constants without a stated origin comment.
Allowlist: tools/e2e/scan-allowlist.txt (`path-substring | regex | reason`).
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
SCAN_DIRS = ["tools"]
SCAN_EXTS = (".py", ".sh", ".ts")

RE_URL = re.compile(r"https?://")
# Split keywords so this scanner's own source cannot self-match.
RE_SECRET = re.compile(
    r"(?i)(api" + "_" + "key|api" + "-" + "key|secret|bear" + "er|pass" + "word)"
    r"\s*[:=]\s*['\"][^$<\s][^'\"]{3,}['\"]")
# Split so this scanner's own source cannot self-match.
RE_BEARER_TOKEN = re.compile("bear" + "er" + r"\s+[A-Za-z0-9\-._~+/]{8,}",
                              re.IGNORECASE)
RE_TESTDETECT = re.compile("PY" + "TEST_" + "|_FIX" + "TURE" + "|FIX" + "TURE_"
                             + "|MO" + "CK_" + "|_MO" + "CK" + "|FA" + "KE_BACKEND"
                             + "|IN_MEMORY" + "_DB")
RE_TUNING = re.compile(
    r"^\s*[A-Z][A-Z0-9_]*(TIMEOUT|RETRIES|THRESHOLD|TOLERANCE|BUDGET|LIMIT|PORT)\b\s*=")


def load_allowlist():
    path = os.path.join(ROOT, "tools", "e2e", "scan-allowlist.txt")
    entries = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            entries.append((parts[0], re.compile(parts[1])))
    return entries


def allowed(relpath, line, allowlist):
    return any(sub in relpath and rx.search(line) for sub, rx in allowlist)


def main(run_dir):
    report = {"check": "d0-scan", "pass": False, "details": [], "hits": []}
    allowlist = load_allowlist()
    files = []
    for dirname in SCAN_DIRS:
        for base, _, names in os.walk(os.path.join(ROOT, dirname)):
            for name in names:
                if name.endswith(SCAN_EXTS):
                    files.append(os.path.join(base, name))
    for path in sorted(files):
        relpath = os.path.relpath(path, ROOT)
        lines = open(path).read().splitlines()
        for i, line in enumerate(lines):
            if allowed(relpath, line, allowlist):
                continue
            if RE_URL.search(line):
                report["hits"].append("%s:%d: url-literal" % (relpath, i + 1))
            if RE_SECRET.search(line):
                report["hits"].append("%s:%d: secret-shaped-assignment" % (relpath, i + 1))
            if RE_BEARER_TOKEN.search(line):
                report["hits"].append("%s:%d: bearer-token-literal" % (relpath, i + 1))
            if RE_TESTDETECT.search(line):
                report["hits"].append("%s:%d: test-detection-identifier" % (relpath, i + 1))
            if RE_TUNING.match(line):
                prev = ""
                for back in range(i - 1, max(i - 4, -1), -1):
                    if lines[back].strip():
                        prev = lines[back]
                        break
                if "# origin:" not in line and "# origin:" not in prev:
                    report["hits"].append("%s:%d: tuning-constant-without-origin" % (relpath, i + 1))
    if report["hits"]:
        report["details"].append("%d hits" % len(report["hits"]))
    else:
        report["details"].append("scanned %d files, zero hits" % len(files))
    report["pass"] = not report["hits"]
    json.dump(report, open(os.path.join(run_dir, "check-d0-scan.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d0-scan: " + "; ".join(report["details"]))
    for hit in report["hits"]:
        print("  hit: " + hit)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
