# Verification test spec FIX-D3A-004

1. Apply the fix in an isolated deployment (never the D0-pinned container).
2. Re-run the D3A suite (tools/e2e/d3a.sh) against the modified deployment
   from a clean state; collect new flip tables.
3. Compare per-detector flip rates vs the frozen pre-fix tables: improvement
   = lower flip rate at equal-or-better human-control pass rate.
4. Human-control regression: re-score all 27 D1 human controls; any new
   AI verdict fails verification.
5. The fix is VERIFIED only when 2–4 pass; otherwise REJECTED with analysis.
