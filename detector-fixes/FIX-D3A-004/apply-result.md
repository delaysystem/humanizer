# Apply result FIX-D3A-004 (d3a-i10) — VERIFIED (spec-literal), DO NOT KEEP

Disposition: VERIFIED — the entry satisfies its verification spec mechanically.
Recommendation: DO NOT KEEP — the flip reduction comes entirely from
uncertainty-shifting with net AI-detection erosion and zero new detections
(see mechanism analysis). Approver: TBD-owner (final keep/discard decision).

## What was applied

- Deployment: image `sloptotal-apply-d3a-i10:a3`
  (`sha256:76fbea8c…`, re-pinned at apply time), container `sloptotal-apply-4`
  (removed after measurement), endpoint `:8770`, patch set
  `build/evidence/APPLY/patch-d3a-i10/` (unified diffs recorded), separate
  models-volume copy (removed). Baseline `sloptotal-d0` untouched.
- Threshold-type only — per-engine slop boundaries moved:
  burstiness 0.65→0.75, classifier_e5 0.65→0.80, gltr 0.65→0.45,
  log_rank 0.65→0.50, readability 0.65→0.75 (sweep candidates, A3
  one-shot protocol).
- Retraining-type NOT-APPLIED: the deployment ships no training code or
  pipeline (weights are downloaded artifacts); augmentation/data specs
  preserved for upstream use.
- Consistency-type NOT-APPLIED as a deployment change: serve-time would
  require generating translation variants per request, and review-routing
  cannot satisfy the flip-rate spec. Batch demo on frozen data would flag
  34 oscillating (detector, original) pairs across intensities
  (`build/evidence/APPLY/oscillation.json`) — analysis, not a fix.

## Measurement

- Boundary proofs 5/5 PROVEN: witness texts from frozen stores scored on
  both endpoints; verdicts flipped exactly as designed while every score,
  the overall score, and the flagged count stayed identical.
- Rescored 27 variants + 54 originals into `results/apply-FIX-D3A-004*/`;
  integrity asserts held (all scores/overall/flagged identical to frozen).
- Flip tables via the frozen `flips.py` CLI.

## Outcome (`build/evidence/APPLY/verify-FIX-D3A-004.json`)

- Flips 6→3: Burstiness 1→0, Readability 2→0 (BERT-tiny RAID, ChatGPT
  Detector, TMR Detector unchanged at 1). Improved: true.
- Human regressions: 0 (humans AI calls 67→58). Human gate: pass.
- Independent recompute match: true. Score diffs: 0. spec_pass: true.

## Mechanism analysis (why DO NOT KEEP)

- Clean counts unchanged (variants 383→383, originals 910→910): nothing
  moved toward detection. Net movement was slop→suspicious (variants
  206→202 slop / 32→36 suspicious; originals 261→246 / 71→86).
- All three vanished flips were removed by original-blinding (AI originals
  leaving slop), not by catching variants. AI-detection deltas:
  Burstiness 2→0 (blinded), E5-Small 16→11 (-31%), Readability 2→0
  (blinded), GLTR 2→3, Log-Rank 5→7.
- The two lowered boundaries (GLTR, Log-Rank) added detections but fixed
  zero flips (both 0→0); the three raised boundaries removed flips only
  by blinding. The frozen binary sweep cannot see the suspicious band, so
  its "fixes" optimize a model that mismatches the three-band deployment.
- Proposed A4 (not applied retroactively): future threshold verifications
  must gate on no-net-AI-detection-loss.

## Evidence

- `build/evidence/APPLY/{remeasure,verify,deploy}-FIX-D3A-004.json`,
  `results/apply-FIX-D3A-004*/`, `build/evidence/APPLY/sweep-d3a-i10.json`.
