# Humanizer

A Bodhan-powered text transformation pipeline plus the local detector-evaluation
harness that was built to validate it. The pipeline rewrites AI-generated text
with translation chains and checks the result against two gates: detection score
**and** semantic fidelity. A rewrite that loses meaning is treated as a defect,
not a success.

This repository grew out of a defensive evaluation of the Sloptotal detector
suite (D0–D6 milestones). The milestone evidence under `build/evidence/` and
`detector-fixes/` records that history.

## How it works

Bodhan's `indic-translate` model is used through its OpenAI-compatible
`POST /v1/chat/completions` endpoint (the `/translate` route is not available in
this deployment). Three strategies are implemented:

- **round-trip** — English → Indic language → English.
- **multi-hop** — English → Indic → Indic → English (e.g. `en → hi → kn → en`).
- **hybrid** — round-trip plus small stylistic normalisations.

The Worker exposes:

| Route | Purpose |
| --- | --- |
| `POST /humanize` | Transform `{ text, strategy?, language?, chain? }` and return the rewritten text with a fidelity score. |
| `POST /queue` | Enqueue a batch humanization job (`MY_QUEUE`). |
| `GET /health`, `GET /` | Health check and service discovery. |

The queue consumer processes submitted jobs asynchronously.

## Layout

- `src/index.ts` — Cloudflare Worker: HTTP routes, queue producer/consumer,
  Bodhan client, fidelity scoring.
- `tools/harness/` — local, config-driven pipeline: translation steps,
  truncation, fidelity scoring, detector flips, evidence storage.
- `tools/apply/` — apply-phase analysis and verification scripts.
- `tools/e2e/` — milestone E2E shells (D0–D6) and verification helpers.
- `config/` — pipeline configuration.
- `datasets/`, `results/`, `detector-fixes/` — evaluation inputs and outputs.

## Requirements

- Node.js / Bun and `wrangler` for the Worker.
- Python 3 with `requirements-fidelity.txt` for the local fidelity scorer
  (`.venv/` and `.models/` are gitignored).
- A Bodhan API key. There are no hardcoded credentials.

## Setup

```bash
bun install

# Local secret (gitignored)
printf 'INDIC_TRANSLATE_API_KEY=<your key>\n' > .dev.vars

bun run dev        # wrangler dev
```

For a deployed Worker:

```sh
bunx wrangler secret put INDIC_TRANSLATE_API_KEY
bun run deploy
```

`BODHAN_API_KEY` is accepted as an alias.

## Verification

```bash
bunx tsc --noEmit                 # typecheck
bash tools/e2e/verify_humanizer.sh # end-to-end verification
```

The E2E suites assert externally observable effects (detector score dumps,
fidelity scores, manifests) written under `build/evidence/`.

## Notes

- Bodhan rate-limits bursts (~20 back-to-back calls/minute). The harness paces
  multi-leg chains and backs off on HTTP 429.
- This project evaluates local detectors only. It does not test or target
  third-party cloud detectors in production.
- Secrets, local `.dev.vars`, Python environments, and generated evidence are
  gitignored. No API keys are committed.

## License

Business Source License 1.1 — see [LICENSE](LICENSE). Non-production use is
granted; the file states the Change Date and Change License.
