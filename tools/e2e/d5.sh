#!/usr/bin/env bash
# tools/e2e/d5.sh — D5 acceptance suite. Regression + reproducibility proofs
# on frozen stores: E2E-3 rescoring (fresh pinned container), E2E-1b regen
# drift (fresh Bodhan calls on a frozen sample), E2E-4 no-humanizer gate,
# E2E-5 scan. The fresh-checkout re-runs are D5 build work (see
# build/evidence/D5/reproducibility.md), not part of this suite script.
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
cfg() { "$PY" -c "import sys; sys.path.insert(0,'tools/harness'); import config as c; print(c.load('$1')['$2'])"; }
export HF_HOME="$PWD/$(cfg fidelity.yaml fidelity_model_cache_dir)"
set -a; . "$(cfg bodhan.yaml bodhan_key_file_local)"; set +a

RUN_DIR="$("$PY" tools/harness/run.py init-run --milestone D5)"
RUN_ID="$(basename "$RUN_DIR")"
echo "run: $RUN_DIR"

# E2E-3: rescore all 207 frozen variants through the pinned-fresh endpoint.
"$PY" tools/analysis/d5_rescore.py --run-dir "$RUN_DIR" \
  --d3-store results/d3 --d3a-store results/d3a

# E2E-1b: regenerate the frozen drift sample with fresh provider calls.
PIPES=cond-rt-kn,cond-truncate-S,d3a-i1,d3a-i3,d3a-i5,d3a-i10,d3a-combo-rt-trunc,d3a-combo-trunc-rt
"$PY" tools/analysis/d5_sample.py --dataset-manifest datasets/v1/manifest.json \
  --pipelines "$PIPES" --seed "$(cfg d5.yaml d5_drift_seed)" \
  --per-n "$(cfg d5.yaml d5_drift_per_condition_n)" --out "$RUN_DIR/drift-sample.json"
for PIPE in cond-rt-kn cond-truncate-S d3a-i1 d3a-i3 d3a-i5 d3a-i10 d3a-combo-rt-trunc d3a-combo-trunc-rt; do
  ONLY="$("$PY" -c "import json; print(','.join(json.load(open('$RUN_DIR/drift-sample.json'))['sample']['$PIPE']))")"
  "$PY" tools/harness/pipeline.py run --pipeline "$PIPE" \
    --dataset-manifest datasets/v1/manifest.json \
    --out "$RUN_DIR/regen-$PIPE" --run-id "$RUN_ID" --store-tag d5regen \
    --only-samples "$ONLY" --no-reuse --no-manifest
done

FAIL=0
"$PY" tools/e2e/checks/d5_rescore.py "$RUN_DIR" results/d3 results/d3a "$RUN_DIR/rescores" || FAIL=1
"$PY" tools/e2e/checks/d5_drift.py "$RUN_DIR" "$RUN_DIR" results/d3 results/d3a "$RUN_DIR/drift-sample.json" || FAIL=1
"$PY" tools/e2e/checks/d5_gate.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D5 SUITE: GREEN ($RUN_DIR)"; else echo "D5 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
