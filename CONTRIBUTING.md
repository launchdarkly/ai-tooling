# Contributing to LaunchDarkly Agent Skills

Thanks for contributing! This repo is a public collection of LaunchDarkly agent skills and playbooks.

## Quick Start

1. Fork and clone the repo.
2. Create a branch for your change.
3. Follow the skill conventions in `docs/skills.md`.
4. Open a PR.

## Adding a New Skill

1. Create a new directory under `skills/`:

```
skills/your-skill-name/
└── SKILL.md
```

2. Copy the template from `template/SKILL.md.template`, rename it to `SKILL.md`, and fill it in.
3. Add any references under a `references/` directory.
4. Update the skill list in `README.md`.
5. Regenerate the catalog: `python3 scripts/generate_catalog.py`.

## Skill Naming Guidelines

- Use lowercase and hyphens only.
- Keep names under 64 characters.
- Make descriptions explicit and keyword-rich.
- If skill is specific to a launchdarkly domain (i.e feature flags, ai configs, etc), please enclose the skills in a directory with the domain name. 

## Local Testing

Point your agent client at the `skills/` directory. Specific setup depends on the client.

### LLM evals (Promptfoo, metrics skills)

The metrics skills have a Promptfoo suite under `tests/`. Run it before merging substantive changes to those skills or the evals (requires an Anthropic API key):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
npm run test:llm-evals
```

Run from the repository root, or from `tests/` with `npm run test:llm-evals` (same as `npm run eval`). For a single skill, use `npm run eval:create`, `eval:choose`, or `eval:instrument` inside `tests/`.

## Documentation

Keep `SKILL.md` under 500 lines. If you need more space, add reference documents.

## Versioning

Update `metadata.version` in `SKILL.md` when the skill behavior changes.
See `docs/versioning.md` for details.

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0 License.
