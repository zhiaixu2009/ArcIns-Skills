# Lessons

## Configuration examples and secrets

- Use unmistakable placeholders such as `<YOUR_IMAGES_API_BASE_URL>` and `<YOUR_API_KEY>` in user-facing configuration examples. Do not use realistic-looking `.example.com` URLs or key-shaped values such as `sk-...`.
- Before publishing, scan tracked files for service-specific API endpoints, API keys, Bearer tokens, and secret-shaped values. Keep required public project links separate from configurable private endpoints.
- Setup helpers must require users to enter their own API endpoint and secret; do not ship a personal or service-specific endpoint as an implicit default.
- Never print or modify ignored local secret files during repository audits. Verify only that they remain untracked and ignored.
- Scan reachable Git history as well as the current tree. Removing a secret from the latest commit does not remove its historical exposure; rotate the credential first, then rewrite and force-push history only with explicit user approval.
