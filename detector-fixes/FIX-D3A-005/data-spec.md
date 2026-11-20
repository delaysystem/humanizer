# Data spec FIX-D3A-005 (retraining-type fix)

- Dataset manifest reference: datasets/d3a/manifest-d3a-combo-rt-trunc.json (frozen version).
- Size: condition variant count per manifest (27 planned).
- Label provenance: inherited AI labels from D1 manifest, verified intact.
- Train/held-out split: to be drawn at apply time (stratified by band);
  the verification set is held out from augmentation training data.
- Quarantine rule: verification on augmentation-training data is leakage
  and invalidates the verification.
