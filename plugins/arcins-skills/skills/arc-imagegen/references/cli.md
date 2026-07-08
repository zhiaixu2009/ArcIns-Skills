# CLI reference (`scripts/image_gen.py`)

This CLI is the primary execution path for `$arc-imagegen`. It calls an OpenAI-compatible Images API through a configurable `base_url` and `api_key`; it does not use Codex's built-in `image_gen` tool.

## Commands

- `generate`: create a new image from a prompt.
- `edit`: edit one or more existing local images.
- `generate-batch`: generate many prompts from a JSONL file.

Use the bundled CLI directly. Do not create one-off runners unless the user explicitly asks for one.

## Configuration

User API configuration should live outside the plugin so plugin updates never overwrite keys. The preferred config file is:

```text
$CODEX_HOME/arc-imagegen/config.json
```

When `CODEX_HOME` is unset, use `%USERPROFILE%\.codex\arc-imagegen\config.json` on Windows or `~/.codex/arc-imagegen/config.json` on macOS/Linux.

Use `--config` only when temporarily overriding the default config:

```powershell
python "<skill-root>/scripts/image_gen.py" generate `
  --config tmp/arc-imagegen/config.toml `
  --prompt "Test" `
  --out "<skill-root>/output/test.png" `
  --dry-run
```

Config lookup order:

1. `--config <path>`
2. `ARC_IMAGEGEN_CONFIG`
3. `$CODEX_HOME/arc-imagegen/config.json`, if present
4. `%USERPROFILE%\.codex\arc-imagegen\config.json` or `~/.codex/arc-imagegen/config.json`, if present
5. `<skill-root>/config.json`, if present
6. Environment overrides: `ARC_IMAGEGEN_BASE_URL`, `ARC_IMAGEGEN_API_KEY`, `ARC_IMAGEGEN_DEFAULT_MODEL`, `ARC_IMAGEGEN_TIMEOUT_SECONDS`

Config may be TOML or JSON:

```json
{
  "base_url": "https://sub-api.example.com",
  "api_key": "sk-...",
  "default_model": "gpt-image-2",
  "timeout_seconds": 300
}
```

The script normalizes bare base URLs to `/v1`, so `https://sub-api.example.com` becomes `https://sub-api.example.com/v1`.

Do not pass API keys on the command line. Dry-runs print `base_url`, endpoint, payload, and output paths, but never print the API key.

## Dependencies

Install bundled dependencies:

```powershell
python -m pip install -r "<skill-root>/requirements.txt"
```

Equivalent individual installs:

```powershell
python -m pip install --user httpx
python -m pip install --user pillow
```

`--dry-run` does not require `httpx`.

## Generate

Dry-run:

```powershell
python "<skill-root>/scripts/image_gen.py" generate `
  --prompt "A cozy alpine cabin at dawn" `
  --size 1024x1024 `
  --dry-run
```

Live call:

```powershell
python "<skill-root>/scripts/image_gen.py" generate `
  --prompt "A cozy alpine cabin at dawn" `
  --quality medium `
  --size 1024x1024 `
  --out "<skill-root>/output/alpine-cabin.png" `
  --stream `
  --quiet
```

Useful options:

- `--model`: defaults to config `default_model`, then `gpt-image-2`.
- `--quality`: `low`, `medium`, `high`, or `auto`; default is `medium`.
- `--size`: `auto` or a valid model size.
- `--n`: 1-15 variants for one prompt.
- `--output-format`: `png`, `jpeg`, or `webp`.
- `--stream`: compatibility flag. All image output requests (`generate`, `generate-batch`, and `edit`) are always sent as event-stream output with `stream=true`, `response_format=b64_json`, and `Accept: text/event-stream`, even when this flag is omitted. The CLI no longer offers synchronous image output because long-running non-streaming requests can sit idle until the final image is ready.
- `--downscale-max-dim`: also write a smaller copy for web usage.
- `--quiet`: suppress routine progress logs while still showing errors.

For multiple requested images, prefer `generate-batch` with one JSONL line per desired output instead of one `generate --n <count>` request. Each batch job is isolated, so completed images remain written even if another job times out.

## Edit

Use `edit` when the user asks to modify existing local images.

```powershell
python "<skill-root>/scripts/image_gen.py" edit `
  --image input.png `
  --prompt "Replace only the background with a warm sunset; keep the product unchanged" `
  --out "<skill-root>/output/sunset-edit.png" `
  --stream
```

Pass multiple `--image` flags in a meaningful order, then describe each image by index and role in the prompt. Use `--mask <png>` for a single edit mask when needed.

## Batch

Create a JSONL file with one prompt or object per line:

```jsonl
{"prompt":"Cavernous hangar interior with a compact shuttle parked near the center","use_case":"stylized-concept","composition":"wide-angle, low-angle","lighting":"volumetric light rays","constraints":"no logos; no watermark","size":"1536x1024"}
{"prompt":"Gray wolf in profile in a snowy forest","use_case":"photorealistic-natural","composition":"eye-level","constraints":"no logos; no watermark","size":"1024x1024"}
```

Run:

```powershell
python "<skill-root>/scripts/image_gen.py" generate-batch `
  --input tmp/imagegen/prompts.jsonl `
  --concurrency 5 `
  --max-attempts 2 `
  --stream `
  --quiet
```

Per-job overrides include `model`, `size`, `quality`, `background`, `output_format`, `output_compression`, `moderation`, `n`, `out`, and all prompt augmentation fields.

`--max-attempts` defaults to `2`: the first request plus one immediate retry for transient failures such as timeouts, connection resets, 429, 408, and 5xx responses. There is no retry cooldown sleep. If the second attempt fails, that job is marked failed and no further retry is attempted.

When `--out-dir` is omitted, batch outputs default to `<skill-root>/output/batch/`.

## Result display

After generation, display every generated file in the Codex conversation with the local image-viewing tool, then list the generated image files in the final text response. Do not create preview helper files, contact sheets, Markdown image embeds, raw HTML previews, or combined preview PNGs.

For routine generation, do not run extra visual QA or post-processing after files are written. Write all user-facing progress and final text in Simplified Chinese. Finish with one concise Chinese sentence that says the count, model, quality, and output directory, followed by compact file links for the generated images.

## gpt-image-2

`gpt-image-2` is the default model.

Use `--quality medium` by default. Use `low` for explicit cheap/fast smoke tests, and `high` for final assets, dense text, diagrams, identity-sensitive edits, or high-resolution output.

Valid `gpt-image-2` sizes are `auto` or any `WIDTHxHEIGHT` satisfying:

- max edge `<= 3840`
- both edges multiples of `16`
- long-to-short ratio `<= 3:1`
- total pixels from `655,360` to `8,294,400`

Common sizes: `1024x1024`, `1536x1024`, `1024x1536`, `2048x2048`, `2048x1152`, `3840x2160`, `2160x3840`.

`gpt-image-2` does not support `--background transparent`; use chroma-key removal first or ask before switching to `gpt-image-1.5` for native transparency.
