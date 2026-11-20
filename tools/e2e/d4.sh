#!/usr/bin/env bash
# tools/e2e/d4.sh — D4 acceptance suite. Offline failure analysis on the
# frozen D3 + D3A stores (no Bodhan calls, no Sloptotal scoring; only
# read-only docker inspect for the no-edit proof). Deterministic: two runs
# produce byte-identical detector-fixes/ + report trees.
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=python3
cfg() { "$PY" -c "import sys; sys.path.insert(0,'tools/harness'); import config as c; print(c.load('$1')['$2'])"; }
RUN3A="$(cfg d4.yaml d4_d3a_tables_run_id)"

RUN_DIR="$("$PY" tools/harness/run.py init-run --milestone D4)"
echo "run: $RUN_DIR"

D3A_TABLES="results/d3a/flip-tables-${RUN3A}.json"
D3A_IDS="results/d3a/failure-ids-${RUN3A}.json"
OUT=build/evidence/D4
FIXES=detector-fixes

"$PY" tools/analysis/d4_analyze.py --d3-store results/d3 --d3a-store results/d3a \
  --originals results/d3a-originals --d3a-tables "$D3A_TABLES" --d3a-ids "$D3A_IDS" \
  --out "$OUT" --fixes "$FIXES"

FAIL=0
"$PY" tools/e2e/checks/d4_repro.py "$RUN_DIR" results/d3 results/d3a results/d3a-originals "$OUT/d4-analysis-report.json" || FAIL=1
"$PY" tools/e2e/checks/d4_fixcomplete.py "$RUN_DIR" results/d3 results/d3a results/d3a-originals "$D3A_IDS" "$OUT/d3-failure-ids.json" "$FIXES" || FAIL=1
"$PY" tools/e2e/checks/d4_index.py "$RUN_DIR" "$FIXES" || FAIL=1
"$PY" tools/e2e/checks/d4_noedit.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d4_honesty.py "$RUN_DIR" "$FIXES" || FAIL=1
"$PY" tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D4 SUITE: GREEN ($RUN_DIR)"; else echo "D4 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
