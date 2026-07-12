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

## Publish and local plugin update

- [x] Confirm the two local `main` commits and the current plugin version.
- [x] Re-run plugin, skill, test, JSON, and dry-run validation.
- [x] Push local `main` to `origin/main` and verify the remote ref.
- [x] Update the Codex-installed `arcins-skills` plugin to the current local source version.
- [x] Verify the active marketplace source, enabled state, and installed cache contents.

### Review

- Corrected the documented upgrade commands to `codex plugin marketplace upgrade arcins` and `codex plugin add arcins-skills@arcins`, matching Codex CLI `0.144.1`.
- Plugin validation, skill validation, both JSON files, the stream dry-run, and all 23 unit tests passed before publishing.
- Pushed local `main` through `4eade13` and verified `origin/main` resolved to the same commit.
- Reinstalled `arcins-skills@arcins`; Codex now reports it as installed and enabled at version `0.1.1`.
- The active `arcins` marketplace points to `E:/7-AgentWorkSpace/arcins-skills`, the cache contains only `0.1.1`, and the installed plugin tree matches the source tree with no diff.

## Root README installation guide

- [x] Audit the existing installation docs and confirm the Codex CLI `0.144.1` plugin command syntax.
- [x] Add a root `README.md` with direct CLI installation, Codex App fallback, dependency setup, API configuration, verification, and upgrade instructions.
- [x] Verify installation from GitHub using an isolated `CODEX_HOME`.
- [x] Validate documentation, plugin metadata, links, and the final diff.
- [x] Commit the README update and push `main` to `origin`.

### Review

- Added a standard root `README.md` so GitHub visitors see installation instructions immediately.
- Documented CLI installation, Codex App fallback, Python dependencies, user-level API configuration, installation verification, and upgrade commands.
- Confirmed the commands against Codex CLI `0.144.1` help output.
- Used a fresh temporary `CODEX_HOME` to add `zhiaixu2009/ArcIns-Skills@main` and install `arcins-skills@arcins`; Codex reported version `0.1.1` as installed and enabled.
- Plugin validation, skill validation, both JSON files, README link targets, `git diff --check`, and all 23 unit tests passed.
- Published the root README in commit `a835699` and verified `origin/main` resolved to the same SHA with the installation guide present.

## Sanitize API configuration examples

- [x] Inventory tracked URLs and secret-shaped values without printing local secret contents.
- [x] Replace user-facing API URLs and key examples with explicit placeholders.
- [x] Remove the service-specific default endpoint from the setup helper and require `base_url` explicitly.
- [x] Re-scan tracked files and verify ignored local configuration remains untracked.
- [x] Run plugin, skill, unit-test, JSON, dry-run, and diff validation.
- [ ] Commit the sanitization changes and push `main` to `origin`.
- [ ] Rotate the historically exposed credential and rewrite affected Git history after explicit approval.

### Review

- Replaced API configuration examples in seven user-facing files with `<YOUR_IMAGES_API_BASE_URL>` and `<YOUR_API_KEY>`.
- Removed the service-specific setup default, made `base_url` required, and stopped the setup helper from echoing the configured URL.
- Added regression coverage for missing `base_url` and URL/key redaction; all 24 unit tests pass.
- Bumped the plugin patch version to `0.1.2` so Codex will not reuse the sanitized content under the old cache version.
- Current tracked non-test files contain no service-specific endpoint, realistic example endpoint, key-shaped credential, or Bearer token. Remaining URLs are required GitHub links and the official OpenAI API default used by runtime code.
- The ignored local `arc-imagegen/config.json` remains untracked and was not printed or modified.
- Git history audit found a non-placeholder, 67-character key-shaped value in `arc-imagegen/config.json` at initial commit `492df70`; it is reachable from local and remote branches. Credential rotation and history rewriting remain pending because they require external action and a destructive force-push decision.
