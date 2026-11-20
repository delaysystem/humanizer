#!/usr/bin/env bash
# tools/e2e/d2.sh — D2 acceptance suite. One command, clean state (fresh run
# directory), real Sloptotal container + real embedding model. Fails fast when
# the D2 venv is missing (documented prerequisite, not a silent skip).
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then echo "D2 requires .venv (see requirements-fidelity.txt)"; exit 2; fi
cfg() { "$PY" -c "import sys; sys.path.insert(0,'tools/harness'); import config as c; print(c.load('$1')['$2'])"; }
export HF_HOME="$PWD/$(cfg fidelity.yaml fidelity_model_cache_dir)"

RUN_DIR="$("$PY" tools/harness/run.py init-run --milestone D2)"
RUN_ID="$(basename "$RUN_DIR")"
echo "run: $RUN_DIR"
REPEATS="$(cfg tolerances.yaml determinism_repeat_n)"
PROBE_SET=build/evidence/D2/probe-set.json
MANIFEST=datasets/v1/manifest.json

"$PY" tools/harness/run.py score-batch --probe-set "$PROBE_SET" --dataset-manifest "$MANIFEST" \
  --out results/d2 --run-id "$RUN_ID" --store-tag d2 --repeats "$REPEATS" --reps-dir "$RUN_DIR/reps"
"$PY" tools/harness/run.py score-batch --probe-set "$PROBE_SET" --dataset-manifest "$MANIFEST" \
  --out results/d2-deadprobe --run-id "$RUN_ID" --store-tag d2dead \
  --base-url "$(cfg api.yaml probe_dead_base_url)" --repeats 1

FAIL=0
"$PY" tools/e2e/checks/d2_scoring.py "$RUN_DIR" results/d2 "$PROBE_SET" || FAIL=1
"$PY" tools/e2e/checks/d2_fidelity.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d2_spread.py "$RUN_DIR" "$RUN_DIR/reps" "$PROBE_SET" || FAIL=1
"$PY" tools/e2e/checks/d2_retry.py "$RUN_DIR" "results/d2/attempts-${RUN_ID}.log" \
  "results/d2-deadprobe/attempts-${RUN_ID}.log" results/d2-deadprobe || FAIL=1
"$PY" tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D2 SUITE: GREEN ($RUN_DIR)"; else echo "D2 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
