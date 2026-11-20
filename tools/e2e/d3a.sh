#!/usr/bin/env bash
# tools/e2e/d3a.sh — D3A acceptance suite. One command, fresh run directory,
# real Bodhan API + real Sloptotal + real embedding model. The shared store
# resumes: config-matching variants/baselines are reused (zero repeat provider
# calls, samples without outputs are processed), so a killed run continues and
# the verifier run re-scores without re-translating. Scoring always runs fresh.
# Long: ~1134 Bodhan calls + ~216 cold Sloptotal scorings (~2 hr). Key loads
# from the vault file named in config (never echoed).
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then echo "D3A requires .venv (see requirements-fidelity.txt)"; exit 2; fi
cfg() { "$PY" -c "import sys; sys.path.insert(0,'tools/harness'); import config as c; print(c.load('$1')['$2'])"; }
export HF_HOME="$PWD/$(cfg fidelity.yaml fidelity_model_cache_dir)"
set -a; . "$(cfg bodhan.yaml bodhan_key_file_local)"; set +a

RUN_DIR="$("$PY" tools/harness/run.py init-run --milestone D3A)"
RUN_ID="$(basename "$RUN_DIR")"
echo "run: $RUN_DIR"
MANIFEST=datasets/v1/manifest.json

"$PY" tools/harness/run.py score-batch --probe-set build/evidence/D3A/originals-probe-set.json \
  --dataset-manifest "$MANIFEST" --out results/d3a-originals --run-id "$RUN_ID" --store-tag d3aorig --repeats 1
for pipe in d3a-i1 d3a-i3 d3a-i5 d3a-i10 d3a-combo-rt-trunc d3a-combo-trunc-rt; do
  "$PY" tools/harness/pipeline.py run --pipeline "$pipe" --dataset-manifest "$MANIFEST" \
    --out results/d3a --run-id "$RUN_ID" --store-tag d3a
done
"$PY" tools/harness/flips.py --store results/d3a --originals results/d3a-originals \
  --out "results/d3a/flip-tables-${RUN_ID}.json" --ids-out "results/d3a/failure-ids-${RUN_ID}.json"

FAIL=0
"$PY" tools/e2e/checks/d3a_completeness.py "$RUN_DIR" results/d3a results/d3a-originals "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3a_preservation.py "$RUN_DIR" results/d3a || FAIL=1
"$PY" tools/e2e/checks/d3_uniqueness.py "$RUN_DIR" results/d3a || FAIL=1
"$PY" tools/e2e/checks/d3a_gating.py "$RUN_DIR" results/d3a "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3_notuning.py "$RUN_DIR" || FAIL=1
"$PY" tools/e2e/checks/d3a_flips.py "$RUN_DIR" results/d3a results/d3a-originals "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3a_fixindex.py "$RUN_DIR" results/d3a "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d3a_budget.py "$RUN_DIR" results/d3a "$RUN_ID" || FAIL=1
"$PY" tools/e2e/checks/d0_scan.py "$RUN_DIR" || FAIL=1

if [ "$FAIL" -eq 0 ]; then echo "D3A SUITE: GREEN ($RUN_DIR)"; else echo "D3A SUITE: RED ($RUN_DIR)"; fi
exit "$FAIL"
