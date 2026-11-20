#!/usr/bin/env bash
# tools/e2e/d6.sh — D6 acceptance suite. Offline final-report verification:
# the generator rebuilds the report + tables from frozen artifacts
# (deterministic: no timestamps, no run IDs), then independent checks verify
# traceability (every number recomputed by a second process), section-3C
# structure, blocked-item carry-forward, and the release checklist.
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=python3

RUN_DIR="$("$PY" tools/harness/run.py init-run --milestone D6)"
echo "run: $RUN_DIR"

"$PY" tools/analysis/d6_report.py --out build/evidence/D6 --report build/FINAL-REPORT.md
sha256sum build/FINAL-REPORT.md build/evidence/D6/final-tables.json \
  build/evidence/D6/traceability.json build/evidence/D6/blocked-items.json \
  > "$RUN_DIR/generation-hashes.txt"

FAIL=0
"$PY" tools/e2e/checks/d6_trace.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d6_tables.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d6_blocked.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d6_gate.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D6 SUITE: GREEN ($RUN_DIR)"; else echo "D6 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
