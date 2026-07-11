# arras-ai

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
```

That one screen surfaces three real risks: the contract is *confirmatorias* (the
buyer **cannot** walk away and keep their options open), it has **no financing
contingency** (if the bank denies the mortgage, the €10,000 is at risk), and it
sets **no deadline** for the deed.

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

Point it at a PDF and it returns a structured analysis:

- **Type of arras** detected, with a confidence score and a justification that
  quotes the deciding clause (or flags that the contract never says).
- **Parties** — names, roles, NIF/NIE/CIF.
- **Amounts** — total price, deposit, and the deposit as a percentage.
- **Dates** — signing date and the deadline (or number of days) for the deed.
- **Property** — address, cadastral reference, registry charges.
- **Código Civil references** actually cited in the text.
- Whether a **financing-contingency clause** is present.

Add `--json` for machine-readable output you can pipe into anything:

```console
$ arras analyze piso_valencia.pdf --json
```

```json
{
  "tipo_arras": "confirmatorias",
  "confianza_tipo": 0.78,
  "justificacion_tipo": "El documento entrega la señal \"a cuenta del precio\"...",
  "importes": { "precio_total": 190000.0, "importe_arras": 10000.0, "porcentaje_arras": 5.26, "moneda": "EUR" },
  "tiene_clausula_financiacion": false,
  "referencias_codigo_civil": []
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

## How it works

Sprint 1 is a deliberately simple, linear pipeline:

```
PDF ──▶ text ──▶ prompt + Pydantic schema ──▶ Claude ──▶ typed analysis ──▶ table / JSON
   pdfplumber        prompts.py                 opus 4.8     structured output
```

- **PDF → text** with `pdfplumber` (MIT-licensed).
- **Extraction & classification** in a single call to Claude using **structured
  outputs**: the model is constrained to a [Pydantic
  schema](src/arras_ai/models.py), so the result is validated, typed data — not
  free text to parse.
- The **prompt** embeds the legal framework (the three modalities, the relevant
  articles, and the "default to confirmatorias when ambiguous" rule) so the
  classification is grounded, not guessed.

Every technical choice — Python, uv, pdfplumber over PyMuPDF (a licensing call),
and the hybrid English-instructions / Spanish-domain prompt strategy — is argued
in [ARCHITECTURE.md](ARCHITECTURE.md).

## Roadmap

Sprint 1 (this) is the foundation. The module boundaries are drawn so each of the
following slots in without a rewrite:

- [x] **Sprint 1 — Foundation.** CLI, robust PDF parsing, structured extraction
      with Claude, typed schema, tests, fixtures.
- [ ] **Sprint 2 — Agent.** Replace the single call with a LangGraph state
      machine (extract → classify → check clauses → assess risk).
- [ ] **Sprint 3 — RAG.** A local vector store of problematic-clause patterns and
      Spanish case law to ground the risk assessment.
- [ ] **Sprint 4 — Evals.** A ground-truth dataset and an LLM-as-judge harness to
      measure accuracy and prevent regressions.
- [ ] **Sprint 5 — Interfaces.** Web UI and a packaged CLI; deployment.
- [ ] **Sprint 6 — MCP server.** Expose the analysis as an MCP tool, plus public
      launch.

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
