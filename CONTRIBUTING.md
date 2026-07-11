# Contributing to arras-ai

Contributions are welcome. This is an early-stage project — issues, fixtures, and
prompt improvements are as valuable as code.

## Getting set up

You need [uv](https://docs.astral.sh/uv/). Then:

```bash
git clone https://github.com/luispique/arras-ai.git
cd arras-ai
uv sync
uv run python scripts/generate_fixtures.py   # create the test PDFs
```

## Before opening a pull request

Run the full check suite locally — CI runs the same thing:

```bash
uv run ruff format .        # format
uv run ruff check .         # lint
uv run mypy                 # type-check (strict)
uv run pytest               # unit tests (offline)
```

If you have an API key and touched the pipeline, also run the integration test:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run pytest -m integration
```

## Guidelines

- **Keep the module seams clean.** `pdf` / `prompts` / `models` / `analyzer` /
  `cli` each have one job (see [ARCHITECTURE.md](ARCHITECTURE.md)). New
  functionality should slot into a stage, not blur the boundaries.
- **Domain stays in Spanish, instructions in English** — see the language
  rationale in ARCHITECTURE.md before changing prompts or schema field names.
- **No real contracts.** Any test fixture must be synthetic or a public template
  with all personal data removed. Prefer well-constructed synthetic contracts.
- **Never commit secrets.** `.env` is git-ignored; use `.env.example` as the
  template.
- **Type everything.** `mypy --strict` must pass.

## Commit messages

Clear, imperative, and scoped. [Conventional
Commits](https://www.conventionalcommits.org/) are encouraged (`feat:`, `fix:`,
`docs:`, `test:`, `chore:`) but not required. Avoid `wip` / `fix stuff`.

## Legal note

By contributing you agree your work is released under the project's
[MIT License](LICENSE). Nothing in this project constitutes legal advice — see
[DISCLAIMER.md](DISCLAIMER.md).
