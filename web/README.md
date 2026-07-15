# arras-ai web demo

Astro frontend + a FastAPI Python service (`/api/analyze`) that reuses the Python core.

The repo deploys as two [Vercel Services](https://vercel.com/docs) declared in the root
`vercel.json`: `web` (this Astro app) and `api` (the FastAPI app at `api/index.py`,
entrypoint `api.index:app`). A rewrite routes `/api/*` to the `api` service and everything
else to `web`. This split is what lets a repo that is itself a Python package still host a
separate frontend without Vercel treating the whole thing as one Python app.

## Local development

```bash
# from the repo root, with the Vercel CLI installed and env vars set (see below):
vercel dev
```

`vercel dev` serves the Astro app and the Python service together. You need, in a
`.env` (or your shell): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`ARRAS_EMBEDDING_PROVIDER=openai`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.

Frontend-only work: `cd web && npm install && npm run dev` (the `/api/analyze` calls
will 404 without `vercel dev`).

## How the demo differs from the core

The self-host core uses local `fastembed` embeddings. The demo uses hosted **OpenAI**
embeddings (no 2 GB model, serverless-friendly) via the same `EmbeddingModel`
interface; the 5-pattern index is built lazily in `/tmp` on the first request.

## Launch checklist (production)

1. `vercel link` this repo to a Vercel project.
2. Set project env vars (Production): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `ARRAS_EMBEDDING_PROVIDER=openai`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.
3. In the Anthropic Console, set a **monthly spend limit** on the key (hard cost cap).
4. In the Vercel dashboard → Firewall, add a **per-IP rate-limit rule** on
   `/api/analyze` (e.g. 5 requests/minute per IP).
5. `vercel deploy --prod`.
6. Confirm a real request returns 200 (not 500) — this validates that `src/`
   (including the `arras_ai/kb_data/` package data) was bundled into the `api`
   service. The service's `root` is the repo root, so `src/` is in scope; the
   `excludeFiles` entry in the root `vercel.json` only prunes `web/`, tests, and
   caches. A 500 with `ModuleNotFoundError: arras_ai` or
   `FileNotFoundError: .../kb_data/...` means the bundle is missing that
   directory.
7. Check the function bundle size against Vercel's Python bundle limit (500 MB
   uncompressed, or higher with Fluid compute) — `lancedb`/`pyarrow` are heavy.
8. Put the resulting URL in the root `README.md` "Try it" section.
