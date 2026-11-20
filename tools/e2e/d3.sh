#!/usr/bin/env bash
# tools/e2e/d3.sh — D3 acceptance suite. One command, fresh run directory,
# real Bodhan API + real Sloptotal + real embedding model. The shared store
# resumes: config-matching variants are reused with zero provider calls (main
# pipelines); probes always re-execute (--no-reuse). Scoring always runs fresh.
# Long: ~45 cold Sloptotal scorings dominate (~20 min). Bodhan key loads from
# the vault file named in config (never echoed).
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then echo "D3 requires .venv (see requirements-fidelity.txt)"; exit 2; fi
cfg() { "$PY" -c "import sys; sys.path.insert(0,'tools/harness'); import config as c; print(c.load('$1')['$2'])"; }
export HF_HOME="$PWD/$(cfg fidelity.yaml fidelity_model_cache_dir)"
set -a; . "$(cfg bodhan.yaml bodhan_key_file_local)"; set +a

RUN_DIR="$("$PY" tools/harness/run.py init-run --milestone D3)"
RUN_ID="$(basename "$RUN_DIR")"
echo "run: $RUN_DIR"
MANIFEST=datasets/v1/manifest.json

"$PY" tools/harness/pipeline.py run --pipeline cond-rt-kn --dataset-manifest "$MANIFEST" \
  --out results/d3 --run-id "$RUN_ID" --store-tag d3
"$PY" tools/harness/pipeline.py run --pipeline cond-truncate-S --dataset-manifest "$MANIFEST" \
  --out results/d3 --run-id "$RUN_ID" --store-tag d3
"$PY" tools/harness/pipeline.py run --pipeline probe-bodhan-fault --dataset-manifest "$MANIFEST" \
  --out results/d3-deadprobe --run-id "$RUN_ID" --store-tag d3dead --no-gate --no-score --no-reuse
"$PY" tools/harness/pipeline.py run --pipeline probe-truncate-v2 --dataset-manifest "$MANIFEST" \
  --out results/d3-replaceprobe --run-id "$RUN_ID" --store-tag d3repl --no-gate --no-score --no-reuse

FAIL=0
"$PY" tools/e2e/checks/d3_completeness.py "$RUN_DIR" results/d3 "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3_preservation.py "$RUN_DIR" results/d3 || FAIL=1
"$PY" tools/e2e/checks/d3_uniqueness.py "$RUN_DIR" results/d3 || FAIL=1
"$PY" tools/e2e/checks/d3_bodhan_fault.py "$RUN_DIR" results/d3-deadprobe "$RUN_ID" results/d3 || FAIL=1
"$PY" tools/e2e/checks/d3_bodhan_budget.py "$RUN_DIR" results/d3 "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3_gating.py "$RUN_DIR" results/d3 "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3_notuning.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d3_replace.py "$RUN_DIR" results/d3-replaceprobe "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3_provenance.py "$RUN_DIR" results/d3 "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D3 SUITE: GREEN ($RUN_DIR)"; else echo "D3 SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
