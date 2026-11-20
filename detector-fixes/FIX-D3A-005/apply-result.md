# Apply result FIX-D3A-005 (d3a-combo-rt-trunc) — VERIFIED (spec-literal), DO NOT KEEP

Disposition: VERIFIED — the entry satisfies its verification spec mechanically.
Recommendation: DO NOT KEEP — the flip reduction comes entirely from
uncertainty-shifting with net AI-detection erosion and zero new detections
(see mechanism analysis). Approver: TBD-owner (final keep/discard decision).

## What was applied

- Deployment: image `sloptotal-apply-d3a-combo-rt-trunc:a3`
  (`sha256:f48392b1…`, re-pinned at apply time), container
  `sloptotal-apply-5` (removed after measurement), endpoint `:8771`,
  patch set `build/evidence/APPLY/patch-d3a-combo-rt-trunc/` (unified
  diffs recorded), separate models-volume copy (removed). Baseline
  `sloptotal-d0` untouched.
- Threshold-type only — per-engine slop boundaries moved:
  burstiness 0.65→0.75, gltr 0.65→0.45 (sweep candidates, A3 one-shot
  protocol). The Readability candidate (T=0.30) was NOT-APPLIED: at/below
  the fixed 0.4 clean boundary it is unrealizable (A3 realizability rule).
- Retraining-type NOT-APPLIED: the deployment ships no training code or
  pipeline (weights are downloaded artifacts); augmentation/data specs
  preserved for upstream use.
- Consistency-type NOT-APPLIED as a deployment change: serve-time would
  require generating translation variants per request, review-routing
  cannot satisfy the flip-rate spec, and combos have no intensity axis
  for the batch demo. Analysis: N/A for this condition.

## Measurement

- Boundary proofs 2/2 PROVEN: witness texts from frozen stores scored on
  both endpoints; verdicts flipped exactly as designed while every score,
  the overall score, and the flagged count stayed identical.
- Rescored 27 variants + 54 originals into `results/apply-FIX-D3A-005*/`;
  integrity asserts held (all scores/overall/flagged identical to frozen).
- Flip tables via the frozen `flips.py` CLI.

## Outcome (`build/evidence/APPLY/verify-FIX-D3A-005.json`)

- Flips 3→2: Burstiness 1→0 (ChatGPT Detector and Readability Uniformity
  unchanged at 1). Improved: true.
- Human regressions: 0 (humans AI calls 67→65). Human gate: pass.
- Independent recompute match: true. Score diffs: 0. spec_pass: true.

## Mechanism analysis (why DO NOT KEEP)

- Clean counts unchanged (variants 349→349, originals 910→910): nothing
  moved toward detection (GLTR widening added slop verdicts but converted
  none to or from clean on the flip pairs).
- The vanished flip was removed by original-blinding (an AI original
  leaving slop), not by catching the variant. AI-detection deltas:
  Burstiness 2→0 (blinded), GLTR 2→3.
- Blinding one detector's AI-original detection entirely to remove a
  single flip is not hardening. The frozen binary sweep cannot see the
  suspicious band, so its "fixes" optimize a model that mismatches the
  three-band deployment.
- Proposed A4 (not applied retroactively): future threshold verifications
  must gate on no-net-AI-detection-loss.

## Evidence

- `build/evidence/APPLY/{remeasure,verify,deploy}-FIX-D3A-005.json`,
  `results/apply-FIX-D3A-005*/`,
  `build/evidence/APPLY/sweep-d3a-combo-rt-trunc.json`.
