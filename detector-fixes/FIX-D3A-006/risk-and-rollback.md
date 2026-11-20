# Risk and rollback FIX-D3A-006

- Expected false-positive impact: retraining on translationese may raise
  human-text scores (translationese resembles non-native prose); the
  verification spec gates on human-control regression for this reason.
- Interaction with other fixes: threshold moves compose nonlinearly with
  retraining; apply and verify entries one at a time.
- Rollback trigger: any verification failure, or human-FPR regression >
  the frozen D4 bound, reverts the deployment to the D0-pinned image.
