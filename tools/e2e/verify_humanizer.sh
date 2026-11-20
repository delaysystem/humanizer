#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "Running Bodhan Humanizer End-to-End Verification Suite"
echo "=========================================================="

cd "$(dirname "$0")/../.."

echo "[1/3] Checking TypeScript / Cloudflare Worker Compilation..."
npx tsc --noEmit
echo "TypeScript compilation: OK"

echo "[2/3] Checking Dependencies..."
.venv/bin/python3 -c "import sentence_transformers, yaml; print('Python dependencies: OK')"

echo "[3/3] Running Real E2E Pipeline (Bodhan API + Fidelity + Sloptotal)..."
.venv/bin/python3 tools/e2e/test_humanizer.py

echo "=========================================================="
echo "ALL VERIFICATION CHECKS PASSED: Bodhan Humanizer Verified."
echo "=========================================================="
