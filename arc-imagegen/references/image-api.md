# Image API quick reference

`$arc-imagegen` calls an OpenAI-compatible Images API through `scripts/image_gen.py`. The intended target is sub2api or another compatible relay configured by `base_url` and `api_key`.

## Endpoints

The CLI uses `httpx` with `base_url` normalized to `/v1`, then calls:

- Generate: `POST /v1/images/generations`
- Edit: `POST /v1/images/edits`

sub2api also registers `/images/generations` and `/images/edits`, but clients should prefer the `/v1/...` form because the CLI normalizes compatible API hosts to `/v1`.

Live requests intentionally send only the necessary compatible headers: Bearer authorization, JSON accept, and `User-Agent: arc-imagegen/1.0`. Do not reintroduce OpenAI SDK generated `x-stainless-*` headers for sub2api calls; some upstream paths block those headers when they are forwarded.

## Authentication

Use Bearer auth from config:

```json
{
  "base_url": "https://sub-api.example.com",
  "api_key": "sk-..."
}
```

Do not pass keys in shell arguments. Fill `<skill-root>/config.json`, or use `--config`, `ARC_IMAGEGEN_CONFIG`, or `ARC_IMAGEGEN_API_KEY`.

## Supported models

The CLI intentionally accepts GPT Image models only:

- `gpt-image-2` (default)
- `gpt-image-1.5`
- `gpt-image-1`
- `gpt-image-1-mini`

If the user needs a non-`gpt-image-*` model, stop and confirm whether the script should be extended. Do not silently bypass model validation.

## Core generation parameters

- `prompt`: required text prompt.
- `model`: image model; defaults to config `default_model`, then `gpt-image-2`.
- `n`: number of variants, 1-15 for this skill.
- `size`: `auto` or a model-supported size.
- `quality`: `low`, `medium`, `high`, or `auto`.
- `background`: `transparent`, `opaque`, or `auto`.
- `output_format`: `png`, `jpeg`, or `webp`.
- `output_compression`: 0-100 for compressed formats.
- `moderation`: forwarded when provided.

Dry-run output includes the resolved `base_url`, endpoint, payload, output paths, and optional downscaled paths. It must not include `api_key`.

## Edit parameters

- `image`: one or more local image files; pass repeated `--image` flags.
- `mask`: optional PNG mask.
- `input_fidelity`: `low` or `high` for models that support it.

For edits, repeat invariants in the prompt: what to change, what must remain unchanged, and what to avoid.

## gpt-image-2 size rules

`gpt-image-2` accepts `auto` or any `WIDTHxHEIGHT` satisfying:

- maximum edge `<= 3840px`
- both edges multiples of `16px`
- long edge to short edge ratio `<= 3:1`
- total pixels between `655,360` and `8,294,400`

Common sizes:

| Label | Size |
| --- | --- |
| Square | `1024x1024` |
| Landscape | `1536x1024` |
| Portrait | `1024x1536` |
| 2K square | `2048x2048` |
| 2K landscape | `2048x1152` |
| 4K landscape | `3840x2160` |
| 4K portrait | `2160x3840` |
| Auto | `auto` |

## Transparency

`gpt-image-2` does not support `background=transparent`. For simple opaque subjects, generate on a flat chroma-key background and remove the key locally with `scripts/remove_chroma_key.py`.

Use `gpt-image-1.5 --background transparent --output-format png` only after user confirmation, unless the user already explicitly requested native/true transparency or `gpt-image-1.5`.

## Response handling

The CLI expects OpenAI Images-style responses with:

```json
{
  "data": [
    {
      "b64_json": "..."
    }
  ]
}
```

The CLI decodes `b64_json` and writes the requested output files. It supports both standard JSON responses and compatible event-stream responses.

For sub2api generation, prefer `--stream`. The server can return `text/event-stream` events such as `image_generation.partial_image` and `image_generation.completed`; the CLI ignores partial images and saves the final completed `b64_json`. This avoids long idle periods on the downstream connection when an upstream image job takes several minutes.

Prompt-only requests such as `{"prompt":"..."}` are classified by sub2api as `images-basic`. Requests with explicit `model`, `size`, `quality`, `output_format`, `stream`, masks, or other native options are classified as `images-native`. The CLI uses the native path when it needs explicit model/options or streaming.

## Failure guidance

- Missing config/key: ask the user to fill `<skill-root>/config.json`, set `ARC_IMAGEGEN_API_KEY`, or provide `--config`.
- Unsupported option for `gpt-image-2`: remove the option only if it is not required; for true transparency, ask before switching to `gpt-image-1.5`.
- Existing output path: reruns fail unless `--force` is passed.
- `httpx` missing: install with `python -m pip install --user httpx`.
