---
name: arc-imagegen
description: Use when the user wants image generation or image editing through a configurable OpenAI-compatible Images API such as sub2api, including when the images are intended for PPT, DOCX, PDF, web pages, posters, mockups, backgrounds, covers, icons, or other downstream artifacts. This skill uses scripts/image_gen.py with base_url/api_key configuration instead of Codex's built-in image_gen tool.
---

# ARC Image Gen

Generate or edit raster images through `scripts/image_gen.py`. This skill is intentionally narrow: convert the user's image intent into a prompt, send it to the configured Images API, save the outputs, and display the generated images in the Codex conversation with the local image-viewing tool.

Do not use Codex's built-in `image_gen` tool from this skill.

## Hard Rules

- If the user wants any image generated, including images for PPT, DOCX, PDF, websites, reports, cards, UI mockups, covers, posters, or other artifacts, use this skill to generate the image directly.
- Do not build a separate PPT, DOCX, PDF, HTML page, canvas, SVG, or local composition workflow unless the user explicitly asks for that artifact after the images are generated.
- Do not split the task into "generate a background, then add text/layout with local scripts" unless the user explicitly asks for local post-processing. Put requested text, layout, style, and composition into the image prompt and generate the image directly.
- Do not create preview helper files, contact sheets, HTML preview pages, Markdown image embeds, HTML image tags, or combined preview PNGs for result presentation.
- Do not perform post-generation visual critique, inspection, repair, or iterative validation unless the user explicitly asks for QA or revisions.
- Keep progress terse. Do not narrate reasoning, dry-run payloads, retry logs, or validation details during routine generation.
- Generate at most 15 images for one user request. If the user asks for more than 15, generate the first 15 and state that the skill limit is 15 per request.
- When the user asks for multiple images, prefer independent jobs through `generate-batch` instead of one `generate --n <count>` API call. This preserves completed images if one request times out.
- All image output requests must use event-stream output. `scripts/image_gen.py` forces `stream=true`, `response_format=b64_json`, and `Accept: text/event-stream` for `generate`, `generate-batch`, and `edit`; do not attempt synchronous image generation or editing.
- For generation retries, use at most 2 attempts per independent image request: the original request plus one immediate retry. Do not wait for retry cooldowns, and do not retry a job again after the second failure.
- If a generation job fails after its second attempt, report that failed job and keep the successfully written images. Do not rerun the same CLI command again unless the user explicitly asks.
- Display every generated image in the Codex conversation by calling the local image-viewing tool on each output file, then list the generated image files in the final text response.
- Use automatic prompt processing by default. If the user explicitly asks for direct image generation, skip prompt analysis and optimization and call the CLI with the user's prompt text.
- Write all user-facing text in Simplified Chinese while using this skill, including progress updates, visible reasoning summaries, final responses, error explanations, and file-list labels. Code, commands, model names, API parameters, filenames, file paths, and exact user-provided direct prompts may stay in their original form.

## Configuration

Path convention: `<skill-root>` means the absolute path to the installed `arc-imagegen` skill directory. User API configuration should live outside the plugin so plugin updates never overwrite keys.

Preferred user config:

```text
$CODEX_HOME/arc-imagegen/config.json
```

When `CODEX_HOME` is unset, use `%USERPROFILE%\.codex\arc-imagegen\config.json` on Windows or `~/.codex/arc-imagegen/config.json` on macOS/Linux.

Supported keys:

```json
{
  "base_url": "<YOUR_IMAGES_API_BASE_URL>",
  "api_key": "<YOUR_API_KEY>",
  "default_model": "gpt-image-2",
  "timeout_seconds": 300
}
```

Lookup order:

1. `--config <path>`
2. `ARC_IMAGEGEN_CONFIG`
3. `$CODEX_HOME/arc-imagegen/config.json`
4. `%USERPROFILE%\.codex\arc-imagegen\config.json` or `~/.codex/arc-imagegen/config.json`
5. `<skill-root>/config.json`
6. `ARC_IMAGEGEN_*` environment variables override file values

Environment overrides:

- `ARC_IMAGEGEN_BASE_URL`
- `ARC_IMAGEGEN_API_KEY`
- `ARC_IMAGEGEN_DEFAULT_MODEL`
- `ARC_IMAGEGEN_TIMEOUT_SECONDS`

Do not pass API keys on the command line.

## Prompt Handling

Use automatic prompt processing by default: Codex may analyze and organize the user's request into a complete image prompt before sending the API request.

Use direct generation only when the user explicitly asks for it in the same message. Accept English or Chinese phrases that clearly mean "direct image generation", "direct send", "send original text", "raw prompt", "do not optimize", "do not rewrite", or "do not modify the prompt".

In direct generation:

- Preserve the user's wording as the `--prompt` value.
- Remove only the skill invocation marker, wrapper command, and explicit direct-generation control phrase, such as `$arc-imagegen` or "direct send", if present.
- Do not add prompt engineering, negative prompts, style descriptors, translations, or inferred details.
- Do not analyze, summarize, improve, expand, or otherwise optimize the image content request.
- Still honor explicit operational controls such as image count, size, quality, model, output path, input image, and mask when they are clearly provided outside the visual prompt.

## Generation Flow

1. Determine whether the user wants generation (`generate`) or editing (`edit`).
2. Build the `--prompt`: use automatic prompt processing by default, or direct generation when the user explicitly requested it.
3. Choose count, size, quality, and output path. Default quality is `medium`; default model is `gpt-image-2`; maximum count is 15.
4. For one new image, run `scripts/image_gen.py generate` with `--quiet`; `--stream` may be included for compatibility but is no longer required because image output requests are always stream-only. For multiple images, create one JSONL job per desired image and run `generate-batch --max-attempts 2 --quiet`. For image editing, run `edit` with the same stream-only invariant.
5. The sub2api images endpoints can keep long-running requests alive through event-stream output, which reduces client-side read timeouts while still saving the final `b64_json` image.
6. After files are written, immediately call the local image-viewing tool once per output image so every generated image appears in the Codex conversation before the final text response.
7. Final response: write one concise Simplified Chinese sentence with model, quality, count, and the output directory, followed by a compact list of the generated image files. Do not include long validation or process details.

## Commands

Generate images:

```powershell
python "<skill-root>/scripts/image_gen.py" generate `
  --prompt "<direct image prompt from the user's intent>" `
  --model gpt-image-2 `
  --quality medium `
  --size 1024x1024 `
  --n 1 `
  --out "<skill-root>/output/output.png" `
  --stream `
  --quiet
```

Edit images:

```powershell
python "<skill-root>/scripts/image_gen.py" edit `
  --image input.png `
  --prompt "<direct edit prompt from the user's intent>" `
  --quality medium `
  --out "<skill-root>/output/edit.png" `
  --stream `
  --quiet
```

Batch generation is available only when the user clearly asks for multiple distinct prompts:

```powershell
python "<skill-root>/scripts/image_gen.py" generate-batch `
  --input prompts.jsonl `
  --out-dir "<skill-root>/output/batch" `
  --concurrency 5 `
  --max-attempts 2 `
  --stream `
  --quiet
```

## First-Run Checks

If generation fails before reaching the API:

- Check that `httpx` is installed, preferably from `<skill-root>/requirements.txt`.
- Check that the Codex user config exists (`$CODEX_HOME/arc-imagegen/config.json` or `~/.codex/arc-imagegen/config.json`) or `ARC_IMAGEGEN_API_KEY` is set.
- Run `python "<skill-root>/scripts/image_gen.py" generate --prompt "test" --dry-run` to verify config resolution without a live request.
- Never ask the user to paste API keys into chat; ask them to edit config or set environment variables.

## Prompt Rules

- Write the prompt for the requested final image, not for an intermediate asset.
- If the user asks for a slide, document, web hero, poster, infographic, app screenshot, cover, ad, or similar visual, describe the final visual in the prompt and generate it directly as an image.
- If exact text is requested inside the image, include the exact text in quotes and specify its placement and style.
- Apply prompt shaping only in the default automatic path. In direct generation, preserve the user's prompt text without content changes except removing the invocation/control phrase.
- Do not propose alternate prompt sets unless the user asks for options.
- Do not ask clarifying questions unless the request lacks the minimum information needed to generate an image. If details are missing but reasonable defaults exist, choose defaults and generate.

## Result Display

Use the local image-viewing tool for all generated images, up to the 15-image limit, then list the generated image files in the final text response. Do not use Markdown image embeds, HTML image tags, gallery files, or combined preview PNGs as the result presentation.

Final response format:

```text
<Simplified Chinese sentence stating count, model, quality, and output directory.>
<Compact file links for every generated image.>
```

Keep it short. Do not use English boilerplate such as "Generated ..." in the final response.

## Reference Map

- `scripts/image_gen.py`: primary API implementation.
- `references/cli.md`: CLI options and examples.
- `references/image-api.md`: Images API parameter notes.
- `references/prompting.md`: prompt shaping guidance.
- `references/sample-prompts.md`: prompt examples.
- `scripts/remove_chroma_key.py`: optional utility only when the user explicitly asks for transparent-background post-processing.
