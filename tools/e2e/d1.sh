#!/usr/bin/env bash
# tools/e2e/d1.sh — D1 acceptance suite. One command, clean state (fresh run
# directory per invocation), real files. No detector scoring in D1 (scope limit).
set -euo pipefail
cd "$(dirname "$0")/../.."

RUN_DIR="$(python3 tools/harness/run.py init-run --milestone D1)"
echo "run: $RUN_DIR"

FAIL=0
for check in manifest balance matched contamination labels; do
  python3 "tools/e2e/checks/d1_${check}.py" "$RUN_DIR" || FAIL=1
done
python3 tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D1 SUITE: GREEN ($RUN_DIR)"; else echo "D1 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
