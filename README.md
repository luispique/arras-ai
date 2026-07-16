# arras-ai

[![CI](https://github.com/luispique/arras-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/luispique/arras-ai/actions/workflows/ci.yml)

**Read your Spanish *contrato de arras* before you sign it.** `arras-ai` takes a
PDF of an earnest-money property contract, extracts the facts that matter, and
tells you which of the three legal modalities it is — grounded in the articles of
the *Código Civil* that decide who loses the deposit if the deal falls through.

It is a command-line tool. It is not a lawyer, and it does not give legal advice
— see the [disclaimer](#legal-disclaimer).

```console
$ arras analyze piso_valencia.pdf
```

```text
╭──────────────────────────────── arras-ai ─────────────────────────────────╮
│ Tipo de arras: confirmatorias  (confianza 78%)                             │
╰────────────────────────────────────────────────────────────────────────────╯
Justificación: El documento entrega la señal "a cuenta del precio" y no
reconoce derecho de desistimiento, propio de arras confirmatorias. No cita
ninguna modalidad expresa.

                     Partes
┌──────────────────────────────────────────────┐
│ Rol       │ Nombre               │ NIF        │
├───────────┼──────────────────────┼────────────┤
│ vendedor  │ Antonio Martínez Gil │ 44556677P  │
│ comprador │ Laura Gómez Torres   │ 11223344Q  │
└──────────────────────────────────────────────┘
                          Datos clave
┌──────────────────────────────────────────────────────────────┐
│ Precio total          │ 190,000.00 EUR                         │
│ Importe arras         │ 10,000.00 EUR                          │
│ % arras               │ 5.3%                                   │
│ Dirección             │ avenida del Puerto 210, 5º, Valencia   │
│ Ref. catastral        │ —                                      │
│ Fecha contrato        │ 2025-04-03                             │
│ Límite escritura      │ —                                      │
│ Cláusula financiación │ no                                     │
└──────────────────────────────────────────────────────────────┘

╭──────────────────────────────── arras-ai ─────────────────────────────────╮
│ Nivel de riesgo global: ALTO                                               │
╰────────────────────────────────────────────────────────────────────────────╯
                                Riesgos detectados
┌───────┬──────────────────────┬───────────────────────────────┬───────────────────────────────┐
│ Sev.  │ Categoría            │ Descripción                   │ Recomendación                 │
├───────┼──────────────────────┼───────────────────────────────┼───────────────────────────────┤
│ alta  │ falta_financiacion   │ No consta cláusula suspensiva │ Incluye condición suspensiva  │
│       │                      │ de financiación...            │ de financiación...            │
│       │                      │                                │ Cf. Cláusula suspensiva de    │
│       │                      │                                │ financiación (buena práctica) │
│ media │ fechas_mal_definidas │ No se fija fecha límite ni    │ Fija una fecha límite         │
│       │                      │ plazo para la escritura...    │ concreta para la escritura... │
└───────┴──────────────────────┴───────────────────────────────┴───────────────────────────────┘
```

That one screen surfaces the same three problems in two forms: the extraction
shows the contract is *confirmatorias* with no financing clause and no deadline,
and the risk report turns that into a **`Nivel de riesgo global: ALTO`** verdict
plus the concrete `alta`-severity risk (no financing contingency — the buyer
**can lose the €10,000** if the bank denies the mortgage) and `media`-severity
risks (no deadline for the deed) that explain why.

## Try it

Live demo: _coming soon_ — see [`web/README.md`](web/README.md) to run it
locally or deploy your own.

---

## The problem

In Spain, before the public deed of sale (*escritura pública*), the buyer and
seller sign a private contract — the **contrato de arras** — where the buyer
hands over a deposit (a *señal*, typically ~10% of the price) and both commit to
completing the sale by a deadline.

There are **three legally distinct kinds of arras**, and the difference decides
what happens if someone backs out:

| Modality | Código Civil | If a party backs out |
| --- | --- | --- |
| **Penitenciales** | art. 1454 | Either party may withdraw. Buyer withdraws → loses the deposit. Seller withdraws → returns it **doubled**. |
| **Confirmatorias** | (general rules) | **No right to withdraw.** The other party can force completion or sue for damages. |
| **Penales** | arts. 1152–1153 | The deposit is a penalty, but the contract is still enforceable — the injured party can demand completion *instead* of keeping the penalty. |

Here is the trap: **if the contract doesn't say which kind it is, Spanish courts
default to *confirmatorias*** — the most binding one. And most arras contracts are
signed without a lawyer, to save the ~€300 fee. They routinely have problems:

- The type of arras is not stated, or is stated ambiguously.
- No financing-contingency clause — so the buyer loses the deposit if the bank
  denies the mortgage.
- Vague or missing deadlines.
- Incomplete property description (no cadastral reference, no mention of
  registry charges).
- Ambiguous split of costs.

`arras-ai` reads the contract and flags these, so you know what to ask a
professional about — or at least what you're signing.

## What this does

Point it at a PDF and it returns a structured analysis plus a risk report:

- **Type of arras** detected, with a confidence score and a justification that
  quotes the deciding clause (or flags that the contract never says).
- **Parties** — names, roles, NIF/NIE/CIF.
- **Amounts** — total price, deposit, and the deposit as a percentage.
- **Dates** — signing date and the deadline (or number of days) for the deed.
- **Property** — address, cadastral reference, registry charges.
- **Código Civil references** actually cited in the text.
- Whether a **financing-contingency clause** is present.
- A **risk report**: an overall `Nivel de riesgo` (`alto`/`medio`/`bajo`) and a
  list of the specific problems found, each with a severity, a description
  quoting what's wrong, and a recommendation of what to ask or fix. A
  well-drafted contract can come back with no risks at all — the tool is
  conservative and only flags genuine problems, not clauses that merely rely on
  the statutory default.

Add `--json` for machine-readable output you can pipe into anything:

```console
$ arras analyze piso_valencia.pdf --json
```

Note: since Sprint 2 the `--json` payload is wrapped in `{analisis, riesgos, nivel_riesgo_global}` (Sprint 1 emitted a flat `AnalisisArras`).

```json
{
  "analisis": {
    "tipo_arras": "confirmatorias",
    "confianza_tipo": 0.78,
    "justificacion_tipo": "El documento entrega la señal \"a cuenta del precio\"...",
    "importes": { "precio_total": 190000.0, "importe_arras": 10000.0, "porcentaje_arras": 5.26, "moneda": "EUR" },
    "tiene_clausula_financiacion": false,
    "referencias_codigo_civil": []
  },
  "riesgos": [
    {
      "categoria": "falta_financiacion",
      "severidad": "alta",
      "descripcion": "No consta cláusula suspensiva de financiación...",
      "recomendacion": "Incluye una condición suspensiva de financiación...",
      "fuente": "regla",
      "referencias": [
        {
          "tipo": "doctrina",
          "referencia": "Cláusula suspensiva de financiación (buena práctica)",
          "texto": "Sin una condición suspensiva de financiación, si la entidad bancaria..."
        }
      ]
    },
    {
      "categoria": "fechas_mal_definidas",
      "severidad": "media",
      "descripcion": "No se fija fecha límite ni plazo para otorgar la escritura pública.",
      "recomendacion": "Fija una fecha límite concreta (o un plazo en días)...",
      "fuente": "regla"
    }
  ],
  "nivel_riesgo_global": "alto"
}
```

## Quick start

You need [uv](https://docs.astral.sh/uv/) and an
[Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/luispique/arras-ai.git
cd arras-ai
uv sync
export ANTHROPIC_API_KEY=sk-ant-...          # or copy .env.example to .env
uv run arras analyze path/to/contrato.pdf
```

Don't have a contract handy? Generate the synthetic test fixtures and try one:

```bash
uv run python scripts/generate_fixtures.py
uv run arras analyze tests/fixtures/arras_confirmatorias_problematic.pdf
```

## Install / self-host

Beyond `uv run` from a clone (above), there are two self-host paths:

**pipx** — installs the CLI into an isolated environment:

```bash
pipx install git+https://github.com/luispique/arras-ai
export ANTHROPIC_API_KEY=sk-ant-...
arras analyze contrato.pdf
```

The first run downloads the local embedding model (`fastembed`, ~2 GB) once;
everything after is offline.

**Docker** — builds a self-contained image (no local Python needed):

```bash
docker build -t arras-ai .
docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... \
  -v "$PWD:/data" -v arras-cache:/cache \
  arras-ai analyze /data/contrato.pdf
```

The first run is slow — it downloads the embedding model into the
`arras-cache` volume — but it's reused on every run after that.

**PyPI**: planned; not yet published.

## Use as an MCP server

`arras-ai` can also run as an [MCP](https://modelcontextprotocol.io/) server over
stdio, so Claude Desktop, Claude Code, or any other MCP client can call it as a
tool:

```bash
pipx install 'arras-ai[mcp] @ git+https://github.com/luispique/arras-ai'
```

Add it to your client's MCP config (e.g. `claude_desktop_config.json`):

```json
{ "mcpServers": { "arras-ai": { "command": "arras-mcp", "env": { "ANTHROPIC_API_KEY": "sk-ant-..." } } } }
```

It exposes two tools, `analizar_contrato_arras` (text in) and
`analizar_contrato_pdf` (a local PDF path in) — both run the same self-host core
with local `fastembed` embeddings, entirely on your machine. Same disclaimer as
everywhere else: not legal advice.

## How it works

A LangGraph agent (`agent.py`) drives a 4-node pipeline from PDF to risk report:

```
PDF ──▶ extraer ──▶ recuperar_contexto ──▶ detectar_riesgos ──▶ componer_informe ──▶ InformeArras
      (Claude,        (semantic search           (rules +              (pure merge:
       structured      over patrones.yaml          one Claude            riesgos,
       output →        in LanceDB, from the         pass for              nivel_riesgo_
       AnalisisArras)   extracted facts)             nuance)                global)
```

- **`extraer`** — PDF text (via `pdfplumber`, MIT-licensed) goes to Claude in a
  single call using **structured outputs**: the model is constrained to a
  [Pydantic schema](src/arras_ai/models.py), so the result is validated, typed
  data (`AnalisisArras`) — not free text to parse. The prompt embeds the legal
  framework (the three modalities, the relevant articles, the "default to
  confirmatorias when ambiguous" rule).
- **`recuperar_contexto`** — retrieves relevant problematic-clause patterns from
  the local knowledge base by semantic similarity, using a query built from the
  facts just extracted (never the raw contract text). See
  [ARCHITECTURE.md](ARCHITECTURE.md#sprint-3-the-rag-knowledge-base-and-citations)
  for why the Código Civil is looked up deterministically instead.
- **`detectar_riesgos`** — deterministic rules check the structured extraction
  for the "obvious" problems (missing type, no financing clause, undefined
  dates, an unidentified property), and a focused Claude pass adds nuance a rule
  can't catch (an ambiguous cost split) plus user-facing recommendations,
  grounded in the retrieved patterns. Each risk carries a `referencias` field
  with the legal fundamentos backing it — rule-based risks always cite the
  relevant Código Civil article or doctrine pattern, while an LLM-found risk
  carries a citation only when it maps to a specific pattern (never a
  fabricated one).
- **`componer_informe`** — merges rule and LLM risks (rules win on overlap) and
  computes an overall `nivel_riesgo_global` (`alto`/`medio`/`bajo`) from the
  worst severity found.

### Knowledge base

The legal content lives in `src/arras_ai/kb_data/` as source YAML —
`codigo_civil.yaml` (the Código Civil articles the tool cites) and
`patrones.yaml` (authored problematic-clause patterns and doctrine) — shipped
as package data, so it's available wherever the package is installed (pip,
pipx, Docker). `patrones.yaml` is embedded into a local LanceDB index the
first time it's needed (or explicitly via `uv run python scripts/build_kb.py`);
the index itself is git-ignored and rebuilt on demand.

Embeddings are **local by default** (`fastembed`, no API key, works offline)
— set `ARRAS_EMBEDDING_PROVIDER=openai` or `voyage` (with the matching API key
and extra installed) to use a hosted provider instead. The default local model
(`intfloat/multilingual-e5-large`) downloads roughly **2 GB** the first time it
runs; this happens once and everything after is fully offline.

LangGraph here is orchestration only — the nodes call Claude directly through
the `anthropic` SDK, not through a LangChain model. See
[ARCHITECTURE.md](ARCHITECTURE.md#sprint-2-the-langgraph-agent-and-risk-detection)
for why, and for every other technical choice — Python, uv, pdfplumber over
PyMuPDF (a licensing call), and the hybrid English-instructions /
Spanish-domain prompt strategy.

## Evals

`evals/` scores the pipeline against `data/evals/casos.yaml`, a set of
synthetic contracts with **by-construction** ground truth (written to match
the contract text as authored, not inferred from a first run — see
[ARCHITECTURE.md](ARCHITECTURE.md#sprint-4-the-eval-harness) for the
reasoning). It measures two different things, on purpose:

- **Deterministic metrics** (no API call): type accuracy, field accuracy
  (amounts, dates, cadastral reference), precision/recall/F1 on detected risk
  categories, and overall risk-level accuracy.
- **LLM-as-judge scores**, from an independent model (`ARRAS_JUDGE_MODEL`,
  default `claude-sonnet-5`, distinct from the analyzer): a 1–5 faithfulness
  score for whether the stated justification for the arras type is grounded
  in the contract text, and a 1–5 score for whether each recommendation is
  pertinent and actionable. The judge never re-decides the type or law itself.

Run it with:

```bash
uv run python scripts/run_evals.py
uv run python scripts/run_evals.py --only minimo --fail-under 0.7
uv run python scripts/run_evals.py --json report.json
```

Example summary (illustrative — real numbers vary run to run, since the
judge's scores are not deterministic):

```text
       Evals — métricas deterministas
┌────────────────────┬─────────┐
│ Métrica             │   Valor │
├────────────────────┼─────────┤
│ tipo_accuracy       │  91.67% │
│ riesgos_f1_micro    │  85.00% │
│ nivel_accuracy      │ 100.00% │
└────────────────────┴─────────┘
        Evals — LLM-as-judge
┌────────────────────────┬───────┐
│ Métrica                 │ Valor │
├────────────────────────┼───────┤
│ fidelidad_media (1-5)    │  4.58 │
│ recomendacion_media (1-5)│  4.33 │
└────────────────────────┴───────┘
casos: 12 · errores: 0 · analizador: claude-opus-4-8 · juez: claude-sonnet-5
```

It needs `ANTHROPIC_API_KEY` for both the analyzer and the judge, and is
deliberately **not** part of the default CI run — every run costs real API
calls against two models. Run it before a release or after changing a prompt.

## Roadmap

Sprint 1 was the foundation; Sprint 2 added the agent and risk detection. The module
boundaries are drawn so each of the following slots in without a rewrite:

- [x] **Sprint 1 — Foundation.** CLI, robust PDF parsing, structured extraction
      with Claude, typed schema, tests, fixtures.
- [x] **Sprint 2 — Agent.** A LangGraph state machine (extract → detect risks →
      compose report) replaces the single call and adds a risk report.
- [x] **Sprint 3 — RAG.** A local vector store of problematic-clause patterns
      and doctrine grounds the LLM risk pass; risks now carry citable legal
      fundamentos (Código Civil articles looked up deterministically, plus the
      retrieved doctrine).
- [x] **Sprint 4 — Evals.** A ground-truth dataset and a hybrid harness
      (deterministic metrics + LLM-as-judge) to measure accuracy and prevent
      regressions.
- [x] **Sprint 5 — Interfaces.** Web demo and CLI/Docker packaging, both done.
- [x] **Sprint 6 — MCP server.** Expose the analysis as an MCP tool, plus public
      launch.
- [x] **Sprint 7 — Privacy.** A local, mask-only PII anonymization layer strips
      identifiers (NIF/NIE/CIF, IBAN, email, phone, cadastral reference) and
      best-effort names from the text before it ever reaches the LLM. Detection is
      always local; nothing personal is sent or restored. **All sprints complete.**

Scope stays narrow on purpose: **only contratos de arras**, no general
conveyancing, rentals, or *notas simples*. Specialisation over breadth.

## Contributing

Issues and pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The
short version: `uv run ruff check . && uv run mypy && uv run pytest` must pass,
and test fixtures must be synthetic (no real personal data).

## Legal disclaimer

**arras-ai is not a lawyer and does not provide legal advice.** It is an
experimental tool whose output is an automated, best-effort interpretation that
**can be wrong** — always verify against the original contract, and consult a
qualified *abogado* or *notario* before acting on any arras contract. The type of
arras has real financial consequences. Full terms (EN/ES) in
[DISCLAIMER.md](DISCLAIMER.md).

## Related work & acknowledgments

The commercial AI contract-review tools — Harvey, Luminance, LegalOn, Ironclad,
Spellbook — target enterprise and law firms, English-language commercial
contracts, and $3k–$8k/year pricing. None focus on Spanish contratos de arras
with the *Código Civil* embedded, and none target individual buyers and small
agencies. This project fills that gap.

Built with [Anthropic Claude](https://www.anthropic.com/) for extraction and
classification, [pdfplumber](https://github.com/jsvine/pdfplumber) for PDF
parsing, and [Pydantic](https://docs.pydantic.dev/) for the typed schema.

## License

[MIT](LICENSE).
