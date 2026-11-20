"""D6 E2E-4 (independent path): release checklist.

Four items, each with an artifact: no-secrets-in-diff (vault untracked +
ignored + absent from diffs; D6 range diff, worktree diff, and untracked
file contents scanned at the D0 scanner bar plus vault-var assignment
outside the vault), no-debug-endpoints (config patterns over product
roots), no-detector-edits (re-executes d4_noedit.py as a subprocess),
no-humanizer-artifact (re-executes d5_gate.py as a subprocess).
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

# Same bar as the D0 scanner (origin: tools/e2e/checks/d0_scan.py); keywords
# are split so this file's own source cannot self-match that scan.
RE_SECRET = re.compile(
    r"(?i)(api" + "_" + "key|api" + "-" + "key|secret|bear" + "er|pass" + "word)"
    r"\s*[:=]\s*['\"][^$<\s][^'\"]{3,}['\"]")
RE_TOKEN = re.compile("bear" + "er" + r"\s+[A-Za-z0-9\-._~+/]{8,}", re.IGNORECASE)
RE_VAULT_VAR = re.compile(r"(?i)BODHAN_[A-Z_]+\s*=\s*\S+")

# Origin: D6 decision — secrets hide in text, and weight/caches live in
# excluded dirs; files above this size are skipped and counted, never read.
MAX_SCAN_BYTES = 1048576


def git(args):
    done = subprocess.run(["git"] + args, cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        raise ValueError("git %s failed: %s" % (" ".join(args), done.stderr.strip()[:200]))
    return done.stdout


def walk(root, exclude_dirs, extensions):
    hits = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in exclude_dirs and not d.startswith("."))
        for name in sorted(files):
            if os.path.splitext(name)[1] in extensions:
                hits.append(os.path.join(base, name))
    return sorted(hits)


def main(run_dir):
    report = {"check": "d6-gate", "pass": False, "details": [], "items": []}
    d6 = cfg.load("d6.yaml")
    bodhan = cfg.load("bodhan.yaml")
    vault = cfg.require_resolved(bodhan, "bodhan_key_file_local", "config/bodhan.yaml")

    # Item 1: no secrets in diff.
    item = {"item": "no-secrets-in-diff", "pass": False, "details": []}
    try:
        bases = git(["log", "--format=%H", "--grep=D5 VERDICT"]).split()
        if len(bases) != 1:
            raise ValueError("expected one D5 VERDICT commit, found %d" % len(bases))
        tracked = git(["ls-files"]).splitlines()
        if vault in tracked or any(t.endswith("/" + vault) for t in tracked):
            raise ValueError("vault %s is tracked" % vault)
        ignored = subprocess.run(["git", "check-ignore", "-q", vault], cwd=ROOT)
        if ignored.returncode != 0:
            raise ValueError("vault %s is not ignored" % vault)
        diff_names = git(["diff", "--name-only", bases[0] + "..HEAD", "--", "."]).splitlines()
        diff_names += git(["diff", "--name-only", "HEAD", "--", "."]).splitlines()
        if vault in diff_names:
            raise ValueError("vault %s appears in a diff" % vault)
        bodies = [git(["diff", bases[0] + "..HEAD", "--", "."]),
                  git(["diff", "HEAD", "--", "."])]
        exclude = set(d6["d6_gate_secret_exclude_dirs"])
        scanned, skipped = 0, 0
        for line in git(["status", "--porcelain"]).splitlines():
            if not line.startswith("??"):
                continue
            rel = line[3:].strip().rstrip("/")
            if rel == vault or rel.split("/")[0] in exclude:
                continue
            full = os.path.join(ROOT, rel)
            if os.path.isdir(full):
                for path in walk(full, exclude, (".py", ".sh", ".ts", ".md", ".yaml",
                                                 ".json", ".txt", ".log")):
                    bodies.append(open(path, errors="replace").read())
                    scanned += 1
            elif os.path.isfile(full):
                if os.path.getsize(full) > MAX_SCAN_BYTES:
                    skipped += 1
                    continue
                bodies.append(open(full, errors="replace").read())
                scanned += 1
        hits = []
        for body in bodies:
            for lineno, text in enumerate(body.splitlines(), 1):
                if RE_SECRET.search(text) or RE_TOKEN.search(text):
                    hits.append("line %d: %s" % (lineno, text.strip()[:80]))
                elif RE_VAULT_VAR.search(text):
                    hits.append("line %d: vault-var outside vault" % lineno)
        if hits:
            raise ValueError("%d secret hits: %s" % (len(hits), "; ".join(hits[:5])))
        item["details"].append("vault untracked+ignored+absent; range %s..HEAD + "
                               "worktree + %d untracked files scanned (%d skipped large)"
                               % (bases[0][:12], scanned, skipped))
        item["pass"] = True
    except ValueError as exc:
        item["details"].append(str(exc))
    report["items"].append(item)

    # Item 2: no debug endpoints.
    item = {"item": "no-debug-endpoints", "pass": False, "details": []}
    try:
        patterns = [re.compile(p) for p in d6["d6_gate_debug_patterns"]]
        hits, scanned = [], 0
        for code_root in d6["d6_gate_debug_roots"]:
            for path in walk(os.path.join(ROOT, code_root), set(), (".py", ".ts", ".sh")):
                scanned += 1
                text = open(path, errors="replace").read()
                for rx in patterns:
                    for lineno, text_line in enumerate(text.splitlines(), 1):
                        if rx.search(text_line):
                            hits.append("%s:%d:%s" % (
                                os.path.relpath(path, ROOT), lineno, text_line.strip()[:80]))
        if hits:
            raise ValueError("%d debug hits: %s" % (len(hits), "; ".join(hits[:5])))
        item["details"].append("%d files over %s clean"
                               % (scanned, ",".join(d6["d6_gate_debug_roots"])))
        item["pass"] = True
    except ValueError as exc:
        item["details"].append(str(exc))
    report["items"].append(item)

    # Items 3-4: re-executed proofs.
    for name, script, check_file in (
            ("no-detector-edits", "d4_noedit.py", "check-d4-noedit.json"),
            ("no-humanizer-artifact", "d5_gate.py", "check-d5-gate.json")):
        item = {"item": name, "pass": False, "details": []}
        try:
            done = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "e2e", "checks", script),
                 run_dir], cwd=ROOT, capture_output=True, text=True, timeout=900)
            proof = os.path.join(run_dir, check_file)
            if done.returncode != 0:
                raise ValueError("%s exited %d: %s"
                                 % (script, done.returncode, done.stderr.strip()[:200]))
            if not os.path.isfile(proof):
                raise ValueError("%s wrote no %s" % (script, check_file))
            verdict = json.load(open(proof))
            if not verdict.get("pass"):
                raise ValueError("%s reports FAIL: %s" % (script, verdict.get("details")))
            item["details"].append("%s green (%s)" % (script, "; ".join(verdict["details"])[:150]))
            item["pass"] = True
        except (ValueError, OSError) as exc:
            item["details"].append(str(exc))
        report["items"].append(item)

    roster = list(d6["d6_release_items"])
    if [i["item"] for i in report["items"]] != roster:
        report["details"].append("checklist items != config roster")
    elif not all(i["pass"] for i in report["items"]):
        report["details"].append("; ".join(
            "%s: %s" % (i["item"], "; ".join(i["details"])) for i in report["items"]
            if not i["pass"]))
    else:
        report["details"].append("all %d release items pass" % len(roster))
        report["pass"] = True
    json.dump(report, open(os.path.join(run_dir, "check-d6-gate.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d6-gate: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
