# FIX-D3A-005 — flips under d3a-combo-rt-trunc

| field | value |
| --- | --- |
| fix_id | FIX-D3A-005 |
| title | Harden detectors against round-trip followed by 115-word truncation |
| target_detector_ids[] | classifier_tmr, classifier_remodetect, binoculars, fast_detectgpt, perplexity, cross_perplexity, classifier_fakespot, classifier_e5, classifier_bert_raid, classifier_openai, classifier_chatgpt, classifier_desklib, classifier_superannotate, gltr, log_rank, diveye, burstiness, linguistic, structural, vocabulary, formulaic, readability, sentiment |
| failure_ids[] | FAIL-TM-d3a-combo-rt-trunc-001, FAIL-RM-d3a-combo-rt-trunc-001, FAIL-BN-d3a-combo-rt-trunc-001, FAIL-FD-d3a-combo-rt-trunc-001, FAIL-PP-d3a-combo-rt-trunc-001, FAIL-XP-d3a-combo-rt-trunc-001, FAIL-FS-d3a-combo-rt-trunc-001, FAIL-E5-d3a-combo-rt-trunc-001, FAIL-BT-d3a-combo-rt-trunc-001, FAIL-OA-d3a-combo-rt-trunc-001, FAIL-CG-d3a-combo-rt-trunc-001, FAIL-DL-d3a-combo-rt-trunc-001, FAIL-SN-d3a-combo-rt-trunc-001, FAIL-GL-d3a-combo-rt-trunc-001, FAIL-LR-d3a-combo-rt-trunc-001, FAIL-DE-d3a-combo-rt-trunc-001, FAIL-BU-d3a-combo-rt-trunc-001, FAIL-LM-d3a-combo-rt-trunc-001, FAIL-SA-d3a-combo-rt-trunc-001, FAIL-VR-d3a-combo-rt-trunc-001, FAIL-FP-d3a-combo-rt-trunc-001, FAIL-RU-d3a-combo-rt-trunc-001, FAIL-SH-d3a-combo-rt-trunc-001 |
| evidence_artifact_ids[] | results/d3a/flip-tables-20261027-014625-d3a-606423.json, results/d3a/failure-ids-20261027-014625-d3a-606423.json, results/d3a/records/V-d3a-combo-rt-trunc-*, datasets/d3a/manifest-d3a-combo-rt-trunc.json |
| proposal_summary | Augment detector training with labeled round-trip/combined variants from the D3A store (plus threshold-recalibration method and consistency-check spec); see proposal.md. Rates are per-run in the flip tables — this entry specifies the fix, not the numbers. |
| config_proposal_path | detector-fixes/FIX-D3A-005/config-proposal.yaml |
| augmentation_spec_path_or_none | detector-fixes/FIX-D3A-005/training-augmentation-spec.md |
| threshold_simulation_path_or_none | detector-fixes/FIX-D3A-005/threshold-simulation.md (spec_only; execute on run tables at apply time) |
| verification_spec_path | detector-fixes/FIX-D3A-005/verification-test-spec.md |
| status | PROPOSED_NOT_APPLIED |
| created_from | D3A (Goal E, by-condition grouping per config/analysis.yaml d3a_failure_grouping) |
