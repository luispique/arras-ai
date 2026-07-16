# arras-ai web demo

Astro frontend + a FastAPI Python API (`/api/analyze`) that reuses the Python core.

The repo deploys as **two Vercel projects from the same repository**:

- **Frontend** (this app) — Vercel project with **Root Directory = `web`**. Scoping the
  root to `web/` hides the repo-root `pyproject.toml`, so Vercel detects Astro cleanly.
  `web/vercel.json` rewrites `/api/*` to the API project's domain (same-origin, no CORS).
- **API** — a separate Vercel project with **Root Directory = repo root**. The FastAPI
  app is `api/index.py`, built as a per-file serverless function; `[tool.vercel]
  entrypoint = "api.index:app"` disambiguates it. `vercel.json` rewrites every path to
  the function (`/(.*)` → `/api/index`) and the app has a catch-all `POST /{path}`, so
  `/api/analyze` is reachable. (The modern root-level single-app Python runtime is
  permission-gated and silently no-ops on this account, so the legacy per-file model is
  used.)

Why two projects: the repo root is itself a Python package, so a single-project deploy
makes Vercel treat the whole repo as one Python app. Vercel's one-project answer for
"frontend + Python backend" is its permission-gated *Services* feature; without that
permission, two projects is the clean GA path.

## Local development

```bash
# from the repo root, with the Vercel CLI installed and env vars set (see below):
vercel dev
```

`vercel dev` serves the Astro app and the Python API together. You need, in a
`.env` (or your shell): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`ARRAS_EMBEDDING_PROVIDER=openai`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.

Frontend-only work: `cd web && npm install && npm run dev` (the `/api/analyze` calls
will 404 without the API deployment / `vercel dev`).

## How the demo differs from the core

The self-host core uses local `fastembed` embeddings. The demo uses hosted **OpenAI**
embeddings (no 2 GB model, serverless-friendly) via the same `EmbeddingModel`
interface; the 5-pattern index is built lazily in `/tmp` on the first request.

## Launch checklist (production)

Two Vercel projects, both pointed at this repo. **Deploy the API first** — the
frontend rewrite needs the API's domain.

**A. API project (Python)**

1. New Vercel project → import this repo → **Root Directory = repo root** (default).
   Vercel detects Python; `[tool.vercel] entrypoint = "api.index:app"` picks the app.
2. Env vars (Production): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `ARRAS_EMBEDDING_PROVIDER=openai`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.
3. In the Anthropic Console, set a **monthly spend limit** on the key (hard cost cap).
4. Deploy. Note the production domain (e.g. `arras-ai-api.vercel.app`).
5. Sanity-check the API directly: `curl -X POST https://<api-domain>/api/analyze
   -H 'content-type: application/json' -d '{"texto":"contrato de arras ..."}'`
   → 200 (not 500). A 500 with `ModuleNotFoundError: arras_ai` or
   `FileNotFoundError: .../kb_data/...` means `src/` / `kb_data` wasn't bundled
   (Python bundles everything under the root by default; `excludeFiles` in `vercel.json`
   only prunes `web/`, tests, and docs).
6. Check the function bundle size against Vercel's Python limit (500 MB uncompressed,
   higher with Fluid compute) — `lancedb`/`pyarrow` are heavy.

**B. Frontend project (Astro)**

7. Set `web/vercel.json`'s rewrite `destination` to the API domain from step 4
   (`https://<api-domain>/api/:path*`).
8. New Vercel project → same repo → **Root Directory = `web`**, Framework = Astro.
9. Deploy. Confirm the page loads and a real analysis returns 200 (the browser calls
   `/api/analyze`, the rewrite proxies it to the API — same-origin, no CORS).
10. In the Vercel dashboard → Firewall, add a **per-IP rate-limit rule** on
    `/api/analyze` (e.g. 5 requests/minute per IP) — on whichever project's domain the
    public traffic hits.
11. Put the frontend URL in the root `README.md` "Try it" section.
