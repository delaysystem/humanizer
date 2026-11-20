# Apply result FIX-D3A-006 (d3a-combo-trunc-rt) — VERIFIED (spec-literal), DO NOT KEEP

Disposition: VERIFIED — the entry satisfies its verification spec mechanically.
Recommendation: DO NOT KEEP — the flip reduction comes entirely from
uncertainty-shifting with net AI-detection erosion and zero new detections
(see mechanism analysis). Approver: TBD-owner (final keep/discard decision).

## What was applied

- Deployment: image `sloptotal-apply-d3a-combo-trunc-rt:a3`
  (`sha256:f99ad5ed…`, re-pinned at apply time), container
  `sloptotal-apply-6` (removed after measurement), endpoint `:8772`,
  patch set `build/evidence/APPLY/patch-d3a-combo-trunc-rt/` (unified
  diffs recorded), separate models-volume copy (removed). Baseline
  `sloptotal-d0` untouched.
- Threshold-type only — per-engine slop boundaries moved:
  burstiness 0.65→0.75, gltr 0.65→0.45, readability 0.65→0.75 (sweep
  candidates, A3 one-shot protocol).
- Retraining-type NOT-APPLIED: the deployment ships no training code or
  pipeline (weights are downloaded artifacts); augmentation/data specs
  preserved for upstream use.
- Consistency-type NOT-APPLIED as a deployment change: serve-time would
  require generating translation variants per request, review-routing
  cannot satisfy the flip-rate spec, and combos have no intensity axis
  for the batch demo. Analysis: N/A for this condition.

## Measurement

- Boundary proofs 3/3 PROVEN: witness texts from frozen stores scored on
  both endpoints; verdicts flipped exactly as designed while every score,
  the overall score, and the flagged count stayed identical.
- Rescored 27 variants + 54 originals into `results/apply-FIX-D3A-006*/`;
  integrity asserts held (all scores/overall/flagged identical to frozen).
- Flip tables via the frozen `flips.py` CLI.

## Outcome (`build/evidence/APPLY/verify-FIX-D3A-006.json`)

- Flips 2→0: Burstiness 1→0, Readability 1→0. Improved: true.
- Human regressions: 0 (humans AI calls 67→65). Human gate: pass.
- Independent recompute match: true. Score diffs: 0. spec_pass: true.

## Mechanism analysis (why DO NOT KEEP)

- Clean counts unchanged (variants 344→344, originals 910→910): nothing
  moved toward detection.
- Both vanished flips were removed by original-blinding (AI originals
  leaving slop), not by catching variants. AI-detection deltas:
  Burstiness 2→0 (blinded), Readability 2→0 (blinded), GLTR 2→3.
- This entry reaches zero flips by blinding two detectors on AI originals
  entirely — the starkest case that the metric-literal pass is not
  hardening. The frozen binary sweep cannot see the suspicious band, so
  its "fixes" optimize a model that mismatches the three-band deployment.
- Proposed A4 (not applied retroactively): future threshold verifications
  must gate on no-net-AI-detection-loss.

## Evidence

- `build/evidence/APPLY/{remeasure,verify,deploy}-FIX-D3A-006.json`,
  `results/apply-FIX-D3A-006*/`,
  `build/evidence/APPLY/sweep-d3a-combo-trunc-rt.json`.
