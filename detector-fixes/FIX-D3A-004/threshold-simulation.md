# Threshold simulation FIX-D3A-004 — SPEC ONLY

- Method (to execute at apply time): sweep per-detector thresholds over the
  logged D3A score snapshot; report flip-rate vs human-FPR tradeoff curve.
- Score-snapshot ID + hash: the committed per-run flip tables + raw store
  (hash at apply time; snapshots differ per run by Bodhan nondeterminism).
- Aggregation formula used: UNKNOWN (provider logistic combination; weights
  not exposed) — ensemble-weighting simulation is UNKNOWN, not estimated.
- Cannot prove: retraining effects, calibration shift, interaction effects
  across fixes, human-control regression. Simulation estimates threshold moves
  on logged scores only; it never validates a fix.
