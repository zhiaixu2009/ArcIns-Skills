# AGENTS.md

This repository is a personal Codex skill library. Treat each top-level skill
folder as an independent, installable skill project.

## Repository Shape

- Each first-level directory is a separate skill, for example `arc-imagegen/`.
- Keep shared root files minimal. The root is for repository-wide guidance,
  ignore rules, and lightweight maintenance files.
- Do not add root-level application code unless the user explicitly asks for a
  shared tool or packaging layer.
- Avoid coupling skills to each other. If one skill needs reusable behavior,
  prefer copying a small script or documenting the dependency clearly instead of
  creating hidden cross-skill imports.

## Skill Folder Convention

Each skill should usually contain:

- `SKILL.md`: required. Include YAML frontmatter with only `name` and
  `description`, followed by concise Markdown instructions.
- `agents/openai.yaml`: recommended UI metadata. Keep it aligned with
  `SKILL.md` whenever the skill changes.
- `scripts/`: optional deterministic helpers for repeated or fragile work.
- `references/`: optional detailed documentation that should be loaded only
  when needed.
- `assets/`: optional files used by the skill's outputs, such as images,
  templates, icons, or boilerplate.
- `tests/`: optional tests for scripts or behavior that can be verified locally.

Use lowercase hyphen-case skill names and folder names, such as
`arc-imagegen`.

## Writing Skills

- Keep `SKILL.md` focused on instructions another Codex instance needs at task
  time.
- Put all trigger conditions in the frontmatter `description`; the body is only
  loaded after the skill triggers.
- Prefer imperative, operational instructions.
- Keep the body concise. Move lengthy examples, API notes, schemas, or domain
  references into `references/`.
- Do not add extra documentation files such as `README.md`,
  `INSTALLATION_GUIDE.md`, `QUICK_REFERENCE.md`, or `CHANGELOG.md` unless the
  user explicitly asks for them.
- Prefer scripts for fragile, repeated, or configuration-heavy operations.
- Test scripts that are added or changed.

## Secrets and Local Config

- Never commit API keys, tokens, local endpoint secrets, or real personal
  configuration.
- Commit `*.example` config files when useful.
- Keep real local config files ignored. The current root `.gitignore` already
  ignores `config.json`, `.env*`, Python caches, virtual environments, build
  outputs, and `arc-imagegen/output/*`.

## Editing Workflow

- Inspect the existing skill before editing it. Follow its local style unless
  the user asks for a broader cleanup.
- Keep changes scoped to the requested skill or root file.
- Do not rewrite unrelated skills while working on one skill.
- Preserve user changes in a dirty worktree.
- Use focused validation after edits:
  - Run relevant unit tests when a skill has tests.
  - Run the changed script directly when behavior depends on a script.
  - Validate `SKILL.md` frontmatter and naming when creating or substantially
    changing a skill.

## Current Skills

### `arc-imagegen`

`arc-imagegen` generates or edits raster images through a configurable
OpenAI-compatible Images API wrapper at `scripts/image_gen.py`.

Important local conventions:

- User-facing responses from this skill should be in Simplified Chinese.
- Do not commit the real `config.json`.
- Generated images belong under `arc-imagegen/output/`, which is ignored.
- Keep `agents/openai.yaml` aligned with the skill's purpose and assets.

