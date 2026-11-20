# Proposal FIX-D3A-002 (d3a-i3)

Failure mode: per-detector decision flips (AI->human, fidelity-passing only)
on variants produced by three en-kn-en rounds (intensity 3). Per-detector flip counts live in the per-run
flip tables; failure IDs (23, one per detector) are the stable references.

Proposed change (spec form; Docker deployment untouched):
1. Retraining-type: augment detector training data with labeled d3a-i3 variants
   (see training-augmentation-spec.md + data-spec.md).
2. Threshold-type: recalibrate per-detector thresholds on logged scores
   (see threshold-simulation.md for method + cannot-prove section).
3. Consistency-type: add a cross-intensity consistency check — flag samples
   whose verdict oscillates across intensities for human review instead of
   trusting the endpoint verdict (spec in config-proposal.yaml).

What stays unknown until the apply phase: post-fix detection rates,
calibration shift, interaction with other fixes, human-control regression.
No claim in this entry asserts a detector is repaired.
