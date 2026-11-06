# AGENTS.md

## Cursor Cloud specific instructions

This repo is not a deployable app. It is a collection of agent **skills** (markdown
playbooks under `skills/`) packaged as Claude Code / Cursor / Codex plugins, plus a
Promptfoo-based LLM eval suite (`evals/`) and Python skill-validation tooling
(`scripts/`, `tests/`). There is no server to run and no build step; `skills.json`
is a generated catalog.

### What you can run without any secrets

These are the CI checks and the fastest way to prove the environment works. Standard
commands are defined in `.github/workflows/validate-skills.yml` and `evals/package.json`:

- Skill validation: `python3 scripts/validate_skills.py` (stdlib only, no pip installs).
- Python unit tests: `python3 -m unittest discover -s tests`.
- Catalog check: `python3 scripts/generate_catalog.py --check` (regenerate without
  `--check` to update `skills.json`).
- Eval harness unit tests: `npm test --prefix evals` (Node `node --test`, no API key).

### Running the LLM evals (`npm run eval` / `npm run eval:all`) — two gotchas

1. **Node version.** Promptfoo requires Node `^20.20.0 || >=22.22.0`. The default
   `node` on PATH here is the pinned `/exec-daemon/node` (currently `v22.14.0`), which
   is too old and makes promptfoo exit immediately. A supported Node 22 is installed
   via nvm; select it before running any promptfoo command in the current shell:
   `export PATH="$HOME/.nvm/versions/node/$(nvm version 22)/bin:$PATH"` (or
   `nvm use 22`). The `node --test` harness unit tests run fine on the default node;
   only the promptfoo CLI needs the newer one.
2. **Anthropic API key.** Both the system-under-test agent and the default rubric
   grader need `ANTHROPIC_API_KEY`. Copy `evals/.env.example` to `evals/.env` and set
   it (`.env` is gitignored). Without it, the harness loads the skill and launches the
   provider but each case errors with "ANTHROPIC_API_KEY environment variable is not
   set". The LaunchDarkly MCP server is mocked during evals
   (`evals/mocks/`), so no LaunchDarkly credentials are needed.

Run all suites from the repo root with `npm run eval` (alias for `eval:all --prefix
evals`); run one suite with `cd evals && npm run eval:<suite>` (e.g. `eval:flag-create`),
or its `:single` variant to smoke-test the first case only. View results with
`npm run eval:view` (Promptfoo UI on port 15500).

Note: `tests/` contains a second, secondary Promptfoo setup; the active suite is
`evals/`.
