# Launch checklist

A short, maintainer-executed checklist for shipping the v0.1.0 launch. No code
changes here — just the steps to run, in order.

## 1. Deploy the web demo

Follow the **Launch checklist (production)** in
[`web/README.md`](../web/README.md#launch-checklist-production): link the Vercel
project, set the production env vars, set the Anthropic key's monthly spend
limit, add the per-IP rate-limit rule on `/api/analyze`, deploy, and confirm a
real request returns 200. Then put the resulting URL in the root
[`README.md`](../README.md) "Try it" section (it currently says "coming soon").

## 2. Tag a release

```bash
git tag v0.1.0
git push --tags
```

Then open a GitHub Release for `v0.1.0` with a short changelog covering the six
sprints: foundation (CLI, PDF, structured extraction), the LangGraph agent and
risk detection, the RAG knowledge base and citations, the eval harness, the web
demo and CLI/Docker packaging, and the MCP server.

## 3. Announcement draft

For Show HN / LinkedIn — factual, no hype, links the repo and the live demo,
and states plainly that it is not legal advice:

> arras-ai reads a Spanish "contrato de arras" (earnest-money property
> contract) and tells you which of the three legally distinct arras types it
> is, plus a risk report grounded in the Código Civil — as a CLI, a web demo,
> or an MCP server. It's an experimental tool, not a lawyer: verify its output
> against the original contract and consult a qualified abogado before acting
> on it. Code: https://github.com/luispique/arras-ai — demo: [URL from step 1].
