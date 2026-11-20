#!/usr/bin/env bash
# tools/e2e/d0.sh — D0 acceptance suite. One command, clean state (fresh run
# directory per invocation), real system (local Sloptotal container + configs).
set -euo pipefail
cd "$(dirname "$0")/../.."

cfg() { python3 -c "import sys; sys.path.insert(0,'tools/harness'); import config as c; print(c.load('$1')['$2'])"; }

NAME="$(cfg api.yaml sloptotal_container_name)"
RUN_DIR="$(python3 tools/harness/run.py init-run --milestone D0)"
echo "run: $RUN_DIR"

BEFORE="$(docker logs "$NAME" 2>&1 | wc -l)"
python3 tools/harness/run.py score --run-dir "$RUN_DIR"
{
  echo "# container-side request capture for the scoring run above"
  docker logs "$NAME" 2>&1 | tail -n "+$((BEFORE + 1))"
} > "$RUN_DIR/container-logs.txt"

FAIL=0
for check in manifest inventory readonly baseline scan; do
  python3 "tools/e2e/checks/d0_${check}.py" "$RUN_DIR" || FAIL=1
done

if [ "$FAIL" -eq 0 ]; then echo "D0 SUITE: GREEN ($RUN_DIR)"; else echo "D0 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
