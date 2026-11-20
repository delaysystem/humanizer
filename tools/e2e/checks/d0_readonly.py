"""D0 E2E-3 (independent path): every captured request is a score/read request.

Capture source is container-side (docker logs), saved to disk by the suite;
this reader parses the saved file. Inbound lines look like:
  INFO:     127.0.0.1:PORT - "METHOD /path PROTO" STATUS
Allowlist comes from config/api.yaml (sloptotal_read_only_paths); a path is
accepted when it equals an entry or starts with an entry ending in '/'.
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg

INBOUND = re.compile(r'"([A-Z]+)\s+(\S+)\s+HTTP/')


def allowed(path, allowlist):
    for entry in allowlist:
        if entry.endswith("/") and path.startswith(entry):
            return True
        if path == entry or path.split("?")[0] == entry:
            return True
    return False


def main(run_dir):
    report = {"check": "d0-readonly", "pass": False, "details": []}
    allowlist = cfg.require_resolved(cfg.load("api.yaml"), "sloptotal_read_only_paths",
                                     "config/api.yaml")
    lines = open(os.path.join(run_dir, "container-logs.txt")).read().splitlines()
    inbound = []
    for line in lines:
        match = INBOUND.search(line)
        if match:
            inbound.append((match.group(1), match.group(2)))
    if not inbound:
        report["details"].append("no inbound request lines captured")
    bad = ["%s %s" % (m, p) for m, p in inbound
           if m not in ("GET", "POST") or not allowed(p, allowlist)]
    if bad:
        report["details"].append("non-read requests: %s" % bad)
    else:
        report["details"].append("%d inbound requests, all read-only per allowlist"
                                 % len(inbound))
    report["pass"] = not bad and bool(inbound)
    json.dump(report, open(os.path.join(run_dir, "check-d0-readonly.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d0-readonly: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
