# Training augmentation spec FIX-D3A-004

- Source: D3A variant store for d3a-i10 (labeled AI variants + fidelity verdicts).
- Selection: fidelity-passing variants only; stratified by length band.
- Labels: ground-truth AI (inherited, verified by d3a preservation check).
- Volume: all passing variants of this condition per frozen dataset version.
- Quarantine: the D3A verification split (see data-spec.md) is held out from
  augmentation training data; verification on training data is leakage.
