# Public marketplace release

- [x] Confirm the public GitHub marketplace and post-install configuration flow.
- [x] Update `arcins-skills.README.md` with public CLI/UI installation, configuration, upgrade, and release instructions.
- [x] Update plugin metadata for a public patch release without adding unverifiable legal or screenshot URLs.
- [x] Validate the plugin, skill, dry-run behavior, tests, JSON, links, and final diff.

## Review

- Public marketplace source remains `.agents/plugins/marketplace.json` with the bundled local plugin path `./plugins/arcins-skills`.
- Plugin manifest validation and `arc-imagegen` skill validation passed.
- All 23 unit tests passed.
- Generate dry-run confirmed `stream: true` and `response_format: b64_json`.
- Both JSON files parse successfully and `git diff --check` reported no whitespace errors.
- The public GitHub remote and `main` ref are reachable. The installed `codex-cli 0.112.0` does not expose plugin commands, so the documentation also provides the Codex App installation path.
- No privacy policy, terms URL, or screenshots were added because no real public assets or legal documents currently exist for those fields.

## Local main merge

- [x] Create a named release branch from the detached worktree and commit the verified changes.
- [x] Merge the release branch into the clean local `main` worktree.
- [x] Re-run focused validation from the local `main` worktree and record the merge result.

### Merge review

- Created `codex/public-marketplace-release` at commit `371d20f`.
- Merged the branch into the local `main` worktree at `E:/7-AgentWorkSpace/arcins-skills`.
- Re-ran plugin validation, skill validation, all 23 unit tests, JSON parsing, and the generate dry-run from local `main`; all passed.
- Local `main` was intentionally not pushed to `origin`.
