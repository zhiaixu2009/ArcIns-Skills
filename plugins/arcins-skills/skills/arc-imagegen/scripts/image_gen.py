#!/usr/bin/env python3
"""API-first CLI for image generation or editing with GPT Image models.

This script calls a configurable OpenAI-compatible Images API such as sub2api
using base_url/api_key settings from config or ARC_IMAGEGEN_* environment
variables.

Defaults to gpt-image-2 and a structured prompt augmentation workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from io import BytesIO

DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "auto"
DEFAULT_QUALITY = "medium"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_CONCURRENCY = 5
DEFAULT_BATCH_MAX_ATTEMPTS = 2
MAX_IMAGES_PER_REQUEST = 15
DEFAULT_DOWNSCALE_SUFFIX = "-web"
DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = DEFAULT_SKILL_ROOT / "output"
DEFAULT_BATCH_OUTPUT_DIR = DEFAULT_OUTPUT_DIR / "batch"
DEFAULT_OUTPUT_PATH = str(DEFAULT_OUTPUT_DIR / "output.png")
DEFAULT_API_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_USER_AGENT = "arc-imagegen/1.0"
DEFAULT_CONFIG_PATH = DEFAULT_SKILL_ROOT / "config.json"
USER_CONFIG_SUBPATH = Path("arc-imagegen") / "config.json"
GPT_IMAGE_MODEL_PREFIX = "gpt-image-"

ALLOWED_LEGACY_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
ALLOWED_QUALITIES = {"low", "medium", "high", "auto"}
ALLOWED_BACKGROUNDS = {"transparent", "opaque", "auto", None}
ALLOWED_INPUT_FIDELITIES = {"low", "high", None}

GPT_IMAGE_2_MODEL = "gpt-image-2"
GPT_IMAGE_2_MIN_PIXELS = 655_360
GPT_IMAGE_2_MAX_PIXELS = 8_294_400
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MAX_RATIO = 3.0

MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_BATCH_JOBS = 500


@dataclass(frozen=True)
class APIConfig:
    base_url: str = DEFAULT_API_BASE_URL
    api_key: str = ""
    default_model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def _die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def _dependency_hint(package: str, *, upgrade: bool = False) -> str:
    command = f"python -m pip install --user {'--upgrade ' if upgrade else ''}{package}"
    return f"Install it with `{command}` in the Python environment used to run this CLI."


def _normalize_base_url(base_url: str) -> str:
    base_url = str(base_url or "").strip().rstrip("/")
    if not base_url:
        return DEFAULT_API_BASE_URL
    if base_url.lower().endswith("/v1"):
        return base_url
    return base_url + "/v1"


def _parse_timeout(value: Any) -> float:
    if value in (None, ""):
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        _die("timeout_seconds must be a number.")
    if timeout <= 0:
        _die("timeout_seconds must be greater than 0.")
    return timeout


def _read_config_data(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        if text.startswith("{"):
            raw = json.loads(text)
        else:
            raw = tomllib.loads(text)
    except Exception as exc:
        _die(f"Failed to parse config file {path}: {exc}")
    if not isinstance(raw, dict):
        _die("Config file must contain a JSON/TOML object.")
    section = raw.get("arc_imagegen") or raw.get("arc-imagegen")
    if isinstance(section, dict):
        merged = dict(raw)
        merged.update(section)
        raw = merged
    return raw


def _codex_home_config_path() -> Optional[Path]:
    raw = os.getenv("CODEX_HOME")
    if not raw:
        return None
    return Path(raw).expanduser() / USER_CONFIG_SUBPATH


def _default_user_config_path() -> Optional[Path]:
    raw = os.getenv("USERPROFILE")
    if raw:
        base = Path(raw).expanduser() / ".codex"
    else:
        try:
            base = Path.home() / ".codex"
        except RuntimeError:
            return None
    return base / USER_CONFIG_SUBPATH


def _candidate_default_config_paths() -> List[Path]:
    candidates: List[Path] = []
    codex_home_config = _codex_home_config_path()
    if codex_home_config is not None:
        candidates.append(codex_home_config)
    user_config = _default_user_config_path()
    if user_config is not None:
        candidates.append(user_config)
    candidates.append(DEFAULT_CONFIG_PATH)

    unique: List[Path] = []
    seen = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _config_path_from_sources(config_path: Optional[str]) -> Optional[Path]:
    if config_path:
        return Path(config_path).expanduser()
    env_config = os.getenv("ARC_IMAGEGEN_CONFIG")
    if env_config:
        return Path(env_config).expanduser()
    for path in _candidate_default_config_paths():
        if path.exists():
            return path
    return None


def _load_api_config(config_path: Optional[str] = None) -> APIConfig:
    path = _config_path_from_sources(config_path)
    data: Mapping[str, Any] = {}
    if path is not None:
        if not path.exists():
            _die(f"Config file not found: {path}")
        data = _read_config_data(path)

    base_url = os.getenv("ARC_IMAGEGEN_BASE_URL") or data.get("base_url") or DEFAULT_API_BASE_URL
    api_key = os.getenv("ARC_IMAGEGEN_API_KEY") or data.get("api_key") or ""
    default_model = (
        os.getenv("ARC_IMAGEGEN_DEFAULT_MODEL")
        or data.get("default_model")
        or DEFAULT_MODEL
    )
    timeout_seconds = _parse_timeout(
        os.getenv("ARC_IMAGEGEN_TIMEOUT_SECONDS") or data.get("timeout_seconds")
    )
    return APIConfig(
        base_url=_normalize_base_url(str(base_url)),
        api_key=str(api_key).strip(),
        default_model=str(default_model).strip() or DEFAULT_MODEL,
        timeout_seconds=timeout_seconds,
    )


def _resolve_api_config(
    *,
    config_path: Optional[str],
    dry_run: bool,
    default_model: Optional[str],
    quiet: bool = False,
) -> APIConfig:
    config = _load_api_config(config_path)
    if default_model:
        config = replace(config, default_model=str(default_model).strip() or DEFAULT_MODEL)
    if config.api_key:
        if not quiet:
            print("ARC Image Gen API key is configured.", file=sys.stderr)
        return config
    if dry_run:
        _warn("ARC Image Gen API key is not configured; dry-run only.")
        return config
    user_config = _default_user_config_path() or Path("~") / ".codex" / USER_CONFIG_SUBPATH
    _die(
        "ARC Image Gen API key is not configured. Set ARC_IMAGEGEN_API_KEY, create "
        f"{user_config}, or run the plugin setup script "
        "plugins/arcins-skills/scripts/setup-arc-imagegen-config.py."
    )


def _read_prompt(prompt: Optional[str], prompt_file: Optional[str]) -> str:
    if prompt and prompt_file:
        _die("Use --prompt or --prompt-file, not both.")
    if prompt_file:
        path = Path(prompt_file)
        if not path.exists():
            _die(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    if prompt:
        return prompt.strip()
    _die("Missing prompt. Use --prompt or --prompt-file.")
    return ""  # unreachable


def _check_image_paths(paths: Iterable[str]) -> List[Path]:
    resolved: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            _die(f"Image file not found: {path}")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            _warn(f"Image exceeds 50MB limit: {path}")
        resolved.append(path)
    return resolved


def _normalize_output_format(fmt: Optional[str]) -> str:
    if not fmt:
        return DEFAULT_OUTPUT_FORMAT
    fmt = fmt.lower()
    if fmt not in {"png", "jpeg", "jpg", "webp"}:
        _die("output-format must be png, jpeg, jpg, or webp.")
    return "jpeg" if fmt == "jpg" else fmt


def _parse_size(size: str) -> Optional[Tuple[int, int]]:
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", size)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _validate_gpt_image_2_size(size: str) -> None:
    if size == "auto":
        return

    parsed = _parse_size(size)
    if parsed is None:
        _die("size must be auto or WIDTHxHEIGHT, for example 1024x1024.")

    width, height = parsed
    max_edge = max(width, height)
    min_edge = min(width, height)
    total_pixels = width * height

    if max_edge > GPT_IMAGE_2_MAX_EDGE:
        _die("gpt-image-2 size maximum edge length must be less than or equal to 3840px.")
    if width % 16 != 0 or height % 16 != 0:
        _die("gpt-image-2 size width and height must be multiples of 16px.")
    if max_edge / min_edge > GPT_IMAGE_2_MAX_RATIO:
        _die("gpt-image-2 size long edge to short edge ratio must not exceed 3:1.")
    if total_pixels < GPT_IMAGE_2_MIN_PIXELS or total_pixels > GPT_IMAGE_2_MAX_PIXELS:
        _die(
            "gpt-image-2 size total pixels must be at least 655,360 and no more than 8,294,400."
        )


def _validate_size(size: str, model: str) -> None:
    if model == GPT_IMAGE_2_MODEL:
        _validate_gpt_image_2_size(size)
        return

    if size not in ALLOWED_LEGACY_SIZES:
        _die(
            "size must be one of 1024x1024, 1536x1024, 1024x1536, or auto for this GPT Image model."
        )


def _validate_quality(quality: str) -> None:
    if quality not in ALLOWED_QUALITIES:
        _die("quality must be one of low, medium, high, or auto.")


def _validate_background(background: Optional[str]) -> None:
    if background not in ALLOWED_BACKGROUNDS:
        _die("background must be one of transparent, opaque, or auto.")


def _validate_input_fidelity(input_fidelity: Optional[str]) -> None:
    if input_fidelity not in ALLOWED_INPUT_FIDELITIES:
        _die("input-fidelity must be one of low or high.")


def _validate_model(model: str) -> None:
    if not model.startswith(GPT_IMAGE_MODEL_PREFIX):
        _die(
            "model must be a GPT Image model (for example gpt-image-1.5, gpt-image-1, or gpt-image-1-mini)."
        )


def _validate_transparency(background: Optional[str], output_format: str) -> None:
    if background == "transparent" and output_format not in {"png", "webp"}:
        _die("transparent background requires output-format png or webp.")


def _validate_model_specific_options(
    *,
    model: str,
    background: Optional[str],
    input_fidelity: Optional[str] = None,
) -> None:
    if model != GPT_IMAGE_2_MODEL:
        return
    if background == "transparent":
        _die(
            "transparent backgrounds are not supported in gpt-image-2, the latest model. "
            "Use --model gpt-image-1.5 --background transparent --output-format png instead."
        )
    if input_fidelity is not None:
        _die(
            "input_fidelity is not supported in gpt-image-2 because image inputs always use high fidelity for this model."
        )


def _validate_generate_payload(payload: Dict[str, Any]) -> None:
    model = str(payload.get("model", DEFAULT_MODEL))
    _validate_model(model)
    n = int(payload.get("n", 1))
    if n < 1 or n > MAX_IMAGES_PER_REQUEST:
        _die(f"n must be between 1 and {MAX_IMAGES_PER_REQUEST}")
    size = str(payload.get("size", DEFAULT_SIZE))
    quality = str(payload.get("quality", DEFAULT_QUALITY))
    background = payload.get("background")
    _validate_size(size, model)
    _validate_quality(quality)
    _validate_background(background)
    _validate_model_specific_options(model=model, background=background)
    oc = payload.get("output_compression")
    if oc is not None and not (0 <= int(oc) <= 100):
        _die("output_compression must be between 0 and 100")


def _build_output_paths(
    out: str,
    output_format: str,
    count: int,
    out_dir: Optional[str],
) -> List[Path]:
    ext = "." + output_format

    if out_dir:
        out_base = Path(out_dir)
        out_base.mkdir(parents=True, exist_ok=True)
        return [out_base / f"image_{i}{ext}" for i in range(1, count + 1)]

    out_path = Path(out)
    if out_path.exists() and out_path.is_dir():
        out_path.mkdir(parents=True, exist_ok=True)
        return [out_path / f"image_{i}{ext}" for i in range(1, count + 1)]

    if out_path.suffix == "":
        out_path = out_path.with_suffix(ext)
    elif output_format and out_path.suffix.lstrip(".").lower() != output_format:
        _warn(
            f"Output extension {out_path.suffix} does not match output-format {output_format}."
        )

    if count == 1:
        return [out_path]

    return [
        out_path.with_name(f"{out_path.stem}-{i}{out_path.suffix}")
        for i in range(1, count + 1)
    ]


def _augment_prompt(args: argparse.Namespace, prompt: str) -> str:
    fields = _fields_from_args(args)
    return _augment_prompt_fields(args.augment, prompt, fields)


def _augment_prompt_fields(augment: bool, prompt: str, fields: Dict[str, Optional[str]]) -> str:
    if not augment:
        return prompt

    sections: List[str] = []
    if fields.get("use_case"):
        sections.append(f"Use case: {fields['use_case']}")
    sections.append(f"Primary request: {prompt}")
    if fields.get("scene"):
        sections.append(f"Scene/background: {fields['scene']}")
    if fields.get("subject"):
        sections.append(f"Subject: {fields['subject']}")
    if fields.get("style"):
        sections.append(f"Style/medium: {fields['style']}")
    if fields.get("composition"):
        sections.append(f"Composition/framing: {fields['composition']}")
    if fields.get("lighting"):
        sections.append(f"Lighting/mood: {fields['lighting']}")
    if fields.get("palette"):
        sections.append(f"Color palette: {fields['palette']}")
    if fields.get("materials"):
        sections.append(f"Materials/textures: {fields['materials']}")
    if fields.get("text"):
        sections.append(f"Text (verbatim): \"{fields['text']}\"")
    if fields.get("constraints"):
        sections.append(f"Constraints: {fields['constraints']}")
    if fields.get("negative"):
        sections.append(f"Avoid: {fields['negative']}")

    return "\n".join(sections)


def _fields_from_args(args: argparse.Namespace) -> Dict[str, Optional[str]]:
    return {
        "use_case": getattr(args, "use_case", None),
        "scene": getattr(args, "scene", None),
        "subject": getattr(args, "subject", None),
        "style": getattr(args, "style", None),
        "composition": getattr(args, "composition", None),
        "lighting": getattr(args, "lighting", None),
        "palette": getattr(args, "palette", None),
        "materials": getattr(args, "materials", None),
        "text": getattr(args, "text", None),
        "constraints": getattr(args, "constraints", None),
        "negative": getattr(args, "negative", None),
    }


def _print_request(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _safe_api_error_message(exc: Exception, config: Optional[APIConfig] = None) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if config is not None and config.api_key:
        message = message.replace(config.api_key, "[redacted]")
    return message


def _die_api_error(exc: Exception, config: Optional[APIConfig] = None) -> None:
    message = _safe_api_error_message(exc, config)
    _die(f"Image API request failed ({exc.__class__.__name__}): {message}")


class ImageAPIError(RuntimeError):
    """Raised when an OpenAI-compatible Images API response cannot be used."""


class ImageAPIHTTPError(ImageAPIError):
    def __init__(self, *, status_code: int, reason: str, body: str, headers: Mapping[str, str]):
        self.status_code = status_code
        self.reason = reason
        self.body = body
        self.headers = headers
        detail = f"HTTP {status_code} {reason}".strip()
        if body:
            detail = f"{detail}: {body}"
        super().__init__(detail)


def _import_httpx():
    try:
        import httpx
    except ImportError:
        _die(f"httpx is required for live API calls. {_dependency_hint('httpx')}")
    return httpx


def _api_headers(config: APIConfig) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }


def _headers_for_json_payload(config: APIConfig, payload: Mapping[str, Any]) -> Dict[str, str]:
    headers = _api_headers(config)
    if payload.get("stream") is True:
        headers["Accept"] = "text/event-stream"
    return headers


def _api_url(config: APIConfig, endpoint: str) -> str:
    endpoint = "/" + endpoint.strip("/")
    return config.base_url.rstrip("/") + endpoint


def _raise_for_api_error(response: Any) -> None:
    if response.status_code < 400:
        return

    body = response.text.strip()
    if len(body) > 2000:
        body = body[:2000] + "...[truncated]"
    raise ImageAPIHTTPError(
        status_code=response.status_code,
        reason=getattr(response, "reason_phrase", ""),
        body=body,
        headers=response.headers,
    )


def _parse_api_json(response: Any) -> Mapping[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        body = response.text.strip()
        if len(body) > 500:
            body = body[:500] + "...[truncated]"
        raise ImageAPIError(f"Expected JSON response, got: {body or response.content!r}") from exc
    if not isinstance(data, dict):
        raise ImageAPIError("Expected JSON object response from Images API.")
    return data


def _is_event_stream_response(response: Any) -> bool:
    content_type = str(response.headers.get("content-type", "")).lower()
    return "text/event-stream" in content_type


def _iter_sse_data_blocks(text: str) -> Iterable[str]:
    data_lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    if data_lines:
        yield "\n".join(data_lines)


def _parse_api_event_stream(response: Any) -> Mapping[str, Any]:
    images: List[str] = []
    fallback_images: List[str] = []
    last_error = ""

    for data_block in _iter_sse_data_blocks(response.text):
        if data_block == "[DONE]":
            continue
        try:
            event = json.loads(data_block)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        error = event.get("error")
        if isinstance(error, dict):
            last_error = str(error.get("message") or error.get("code") or error)
            continue
        event_type = str(event.get("type", "")).lower()
        image_b64 = event.get("b64_json")
        if not isinstance(image_b64, str) or not image_b64:
            continue
        if "partial" in event_type:
            continue
        if "completed" in event_type or not event_type:
            images.append(image_b64)
        else:
            fallback_images.append(image_b64)

    if not images:
        images = fallback_images
    if not images:
        detail = f": {last_error}" if last_error else ""
        raise ImageAPIError(f"Images API event stream did not contain a completed b64_json image{detail}.")
    return {"data": [{"b64_json": image_b64} for image_b64 in images]}


def _extract_b64_images(response_data: Mapping[str, Any]) -> List[str]:
    items = response_data.get("data")
    if not isinstance(items, list) or not items:
        raise ImageAPIError("Images API response did not contain a non-empty data array.")

    images: List[str] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ImageAPIError(f"Images API data item {idx} is not an object.")
        image_b64 = item.get("b64_json")
        if not isinstance(image_b64, str) or not image_b64:
            raise ImageAPIError(f"Images API data item {idx} did not contain b64_json.")
        images.append(image_b64)
    return images


def _http_client_kwargs(config: APIConfig, transport: Any = None) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "headers": _api_headers(config),
        "timeout": config.timeout_seconds,
    }
    if transport is not None:
        kwargs["transport"] = transport
    return kwargs


def _post_json_api(
    config: APIConfig,
    endpoint: str,
    payload: Mapping[str, Any],
    *,
    transport: Any = None,
) -> Mapping[str, Any]:
    httpx = _import_httpx()
    kwargs = _http_client_kwargs(config, transport)
    kwargs["headers"] = _headers_for_json_payload(config, payload)
    with httpx.Client(**kwargs) as client:
        response = client.post(_api_url(config, endpoint), json=dict(payload))
    _raise_for_api_error(response)
    if _is_event_stream_response(response):
        return _parse_api_event_stream(response)
    return _parse_api_json(response)


async def _post_json_api_async(
    client: Any,
    config: APIConfig,
    endpoint: str,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    response = await client.post(
        _api_url(config, endpoint),
        json=dict(payload),
        headers=_headers_for_json_payload(config, payload),
    )
    _raise_for_api_error(response)
    if _is_event_stream_response(response):
        return _parse_api_event_stream(response)
    return _parse_api_json(response)


def _create_async_http_client(config: APIConfig) -> Any:
    httpx = _import_httpx()
    return httpx.AsyncClient(**_http_client_kwargs(config))


def _form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _post_edit_api(
    config: APIConfig,
    payload: Mapping[str, Any],
    image_paths: List[Path],
    mask_path: Optional[Path],
    *,
    transport: Any = None,
) -> Mapping[str, Any]:
    httpx = _import_httpx()
    stream_payload = _force_image_stream(dict(payload))
    data = {key: _form_value(value) for key, value in stream_payload.items()}
    handles: List[Any] = []
    files: List[Tuple[str, Tuple[str, Any, str]]] = []

    try:
        for image_path in image_paths:
            handle = image_path.open("rb")
            handles.append(handle)
            files.append(
                ("image", (image_path.name, handle, _guess_mime_type(image_path)))
            )
        if mask_path is not None:
            handle = mask_path.open("rb")
            handles.append(handle)
            files.append(("mask", (mask_path.name, handle, _guess_mime_type(mask_path))))

        kwargs = _http_client_kwargs(config, transport)
        kwargs["headers"] = _headers_for_json_payload(config, stream_payload)
        with httpx.Client(**kwargs) as client:
            response = client.post(_api_url(config, "/images/edits"), data=data, files=files)
    finally:
        for handle in handles:
            try:
                handle.close()
            except Exception:
                pass

    _raise_for_api_error(response)
    if _is_event_stream_response(response):
        return _parse_api_event_stream(response)
    return _parse_api_json(response)


def _decode_and_write(
    images: List[str],
    outputs: List[Path],
    force: bool,
    *,
    quiet: bool = False,
) -> None:
    for idx, image_b64 in enumerate(images):
        if idx >= len(outputs):
            break
        out_path = outputs[idx]
        if out_path.exists() and not force:
            _die(f"Output already exists: {out_path} (use --force to overwrite)")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(image_b64))
        if not quiet:
            print(f"Wrote {out_path}")


def _derive_downscale_path(path: Path, suffix: str) -> Path:
    if suffix and not suffix.startswith("-") and not suffix.startswith("_"):
        suffix = "-" + suffix
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def _downscale_image_bytes(image_bytes: bytes, *, max_dim: int, output_format: str) -> bytes:
    try:
        from PIL import Image
    except Exception:
        _die(f"Downscaling requires Pillow. {_dependency_hint('pillow')}")

    if max_dim < 1:
        _die("--downscale-max-dim must be >= 1")

    with Image.open(BytesIO(image_bytes)) as img:
        img.load()
        w, h = img.size
        scale = min(1.0, float(max_dim) / float(max(w, h)))
        target = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))

        resized = img if target == (w, h) else img.resize(target, Image.Resampling.LANCZOS)

        fmt = output_format.lower()
        if fmt == "jpg":
            fmt = "jpeg"

        if fmt == "jpeg":
            if resized.mode in ("RGBA", "LA") or ("transparency" in getattr(resized, "info", {})):
                bg = Image.new("RGB", resized.size, (255, 255, 255))
                bg.paste(resized.convert("RGBA"), mask=resized.convert("RGBA").split()[-1])
                resized = bg
            else:
                resized = resized.convert("RGB")

        out = BytesIO()
        resized.save(out, format=fmt.upper())
        return out.getvalue()


def _decode_write_and_downscale(
    images: List[str],
    outputs: List[Path],
    *,
    force: bool,
    downscale_max_dim: Optional[int],
    downscale_suffix: str,
    output_format: str,
    quiet: bool = False,
) -> None:
    for idx, image_b64 in enumerate(images):
        if idx >= len(outputs):
            break
        out_path = outputs[idx]
        if out_path.exists() and not force:
            _die(f"Output already exists: {out_path} (use --force to overwrite)")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        raw = base64.b64decode(image_b64)
        out_path.write_bytes(raw)
        if not quiet:
            print(f"Wrote {out_path}")

        if downscale_max_dim is None:
            continue

        derived = _derive_downscale_path(out_path, downscale_suffix)
        if derived.exists() and not force:
            _die(f"Output already exists: {derived} (use --force to overwrite)")
        derived.parent.mkdir(parents=True, exist_ok=True)
        resized = _downscale_image_bytes(raw, max_dim=downscale_max_dim, output_format=output_format)
        derived.write_bytes(resized)
        if not quiet:
            print(f"Wrote {derived}")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:60] if value else "job"


def _normalize_job(job: Any, idx: int) -> Dict[str, Any]:
    if isinstance(job, str):
        prompt = job.strip()
        if not prompt:
            _die(f"Empty prompt at job {idx}")
        return {"prompt": prompt}
    if isinstance(job, dict):
        if "prompt" not in job or not str(job["prompt"]).strip():
            _die(f"Missing prompt for job {idx}")
        return job
    _die(f"Invalid job at index {idx}: expected string or object.")
    return {}  # unreachable


def _read_jobs_jsonl(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        _die(f"Input file not found: {p}")
    jobs: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item: Any
            if line.startswith("{"):
                item = json.loads(line)
            else:
                item = line
            jobs.append(_normalize_job(item, idx=line_no))
        except json.JSONDecodeError as exc:
            _die(f"Invalid JSON on line {line_no}: {exc}")
    if not jobs:
        _die("No jobs found in input file.")
    if len(jobs) > MAX_BATCH_JOBS:
        _die(f"Too many jobs ({len(jobs)}). Max is {MAX_BATCH_JOBS}.")
    return jobs


def _merge_non_null(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(dst)
    for k, v in src.items():
        if v is not None:
            merged[k] = v
    return merged


def _force_image_stream(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload["stream"] = True
    payload["response_format"] = "b64_json"
    return payload


def _job_output_paths(
    *,
    out_dir: Path,
    output_format: str,
    idx: int,
    prompt: str,
    n: int,
    explicit_out: Optional[str],
) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "." + output_format

    if explicit_out:
        base = Path(explicit_out)
        if base.suffix == "":
            base = base.with_suffix(ext)
        elif base.suffix.lstrip(".").lower() != output_format:
            _warn(
                f"Job {idx}: output extension {base.suffix} does not match output-format {output_format}."
            )
        base = out_dir / base.name
    else:
        slug = _slugify(prompt[:80])
        base = out_dir / f"{idx:03d}-{slug}{ext}"

    if n == 1:
        return [base]
    return [
        base.with_name(f"{base.stem}-{i}{base.suffix}")
        for i in range(1, n + 1)
    ]


def _is_rate_limit_error(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    name = exc.__class__.__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def _is_transient_error(exc: Exception) -> bool:
    if _is_rate_limit_error(exc):
        return True
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {408, 409, 425} or status_code >= 500
    name = exc.__class__.__name__.lower()
    if "timeout" in name or "timedout" in name or "tempor" in name:
        return True
    msg = str(exc).lower()
    return "timeout" in msg or "timed out" in msg or "connection reset" in msg


async def _generate_one_with_retries(
    client: Any,
    config: APIConfig,
    payload: Dict[str, Any],
    *,
    attempts: int,
    job_label: str,
    quiet: bool = False,
) -> List[str]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            response_data = await _post_json_api_async(
                client,
                config,
                "/images/generations",
                payload,
            )
            return _extract_b64_images(response_data)
        except Exception as exc:
            last_exc = exc
            if not _is_transient_error(exc):
                raise
            if attempt == attempts:
                raise
            if not quiet:
                print(
                    f"{job_label} attempt {attempt}/{attempts} failed ({exc.__class__.__name__}); retrying now",
                    file=sys.stderr,
                )
    raise last_exc or RuntimeError("unknown error")


async def _run_generate_batch(args: argparse.Namespace) -> int:
    jobs = _read_jobs_jsonl(args.input)
    out_dir = Path(args.out_dir)

    base_fields = _fields_from_args(args)
    base_payload = {
        "model": args.model,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "moderation": args.moderation,
    }
    _force_image_stream(base_payload)

    if args.dry_run:
        for i, job in enumerate(jobs, start=1):
            prompt = str(job["prompt"]).strip()
            fields = _merge_non_null(base_fields, job.get("fields", {}))
            # Allow flat job keys as well (use_case, scene, etc.)
            fields = _merge_non_null(fields, {k: job.get(k) for k in base_fields.keys()})
            augmented = _augment_prompt_fields(args.augment, prompt, fields)

            job_payload = dict(base_payload)
            job_payload["prompt"] = augmented
            job_payload = _merge_non_null(job_payload, {k: job.get(k) for k in base_payload.keys()})
            job_payload = {k: v for k, v in job_payload.items() if v is not None}
            _force_image_stream(job_payload)

            _validate_generate_payload(job_payload)
            effective_output_format = _normalize_output_format(job_payload.get("output_format"))
            _validate_transparency(job_payload.get("background"), effective_output_format)
            job_payload["output_format"] = effective_output_format

            n = int(job_payload.get("n", 1))
            outputs = _job_output_paths(
                out_dir=out_dir,
                output_format=effective_output_format,
                idx=i,
                prompt=prompt,
                n=n,
                explicit_out=job.get("out"),
            )
            downscaled = None
            if args.downscale_max_dim is not None:
                downscaled = [
                    str(_derive_downscale_path(p, args.downscale_suffix)) for p in outputs
                ]
            _print_request(
                {
                    "base_url": args.api_config.base_url,
                    "endpoint": "/v1/images/generations",
                    "job": i,
                    "outputs": [str(p) for p in outputs],
                    "outputs_downscaled": downscaled,
                    **job_payload,
                }
            )
        return 0

    client = _create_async_http_client(args.api_config)
    sem = asyncio.Semaphore(args.concurrency)

    any_failed = False

    async def run_job(i: int, job: Dict[str, Any]) -> Tuple[int, Optional[str]]:
        nonlocal any_failed
        prompt = str(job["prompt"]).strip()
        job_label = f"[job {i}/{len(jobs)}]"

        fields = _merge_non_null(base_fields, job.get("fields", {}))
        fields = _merge_non_null(fields, {k: job.get(k) for k in base_fields.keys()})
        augmented = _augment_prompt_fields(args.augment, prompt, fields)

        payload = dict(base_payload)
        payload["prompt"] = augmented
        payload = _merge_non_null(payload, {k: job.get(k) for k in base_payload.keys()})
        payload = {k: v for k, v in payload.items() if v is not None}
        _force_image_stream(payload)

        n = int(payload.get("n", 1))
        _validate_generate_payload(payload)
        effective_output_format = _normalize_output_format(payload.get("output_format"))
        _validate_transparency(payload.get("background"), effective_output_format)
        payload["output_format"] = effective_output_format
        outputs = _job_output_paths(
            out_dir=out_dir,
            output_format=effective_output_format,
            idx=i,
            prompt=prompt,
            n=n,
            explicit_out=job.get("out"),
        )
        try:
            async with sem:
                if not args.quiet:
                    print(f"{job_label} starting", file=sys.stderr)
                started = time.time()
                images = await _generate_one_with_retries(
                    client,
                    args.api_config,
                    payload,
                    attempts=args.max_attempts,
                    job_label=job_label,
                    quiet=args.quiet,
                )
                elapsed = time.time() - started
                if not args.quiet:
                    print(f"{job_label} completed in {elapsed:.1f}s", file=sys.stderr)
            _decode_write_and_downscale(
                images,
                outputs,
                force=args.force,
                downscale_max_dim=args.downscale_max_dim,
                downscale_suffix=args.downscale_suffix,
                output_format=effective_output_format,
                quiet=args.quiet,
            )
            return i, None
        except Exception as exc:
            any_failed = True
            safe_message = _safe_api_error_message(exc, args.api_config)
            print(f"{job_label} failed: {safe_message}", file=sys.stderr)
            if args.fail_fast:
                raise
            return i, safe_message

    try:
        tasks = [asyncio.create_task(run_job(i, job)) for i, job in enumerate(jobs, start=1)]
        try:
            await asyncio.gather(*tasks)
        except Exception:
            for t in tasks:
                if not t.done():
                    t.cancel()
            raise
    except Exception:
        raise
    finally:
        await client.aclose()

    return 1 if any_failed else 0


def _generate_batch(args: argparse.Namespace) -> None:
    try:
        exit_code = asyncio.run(_run_generate_batch(args))
    except Exception as exc:
        _die_api_error(exc, getattr(args, "api_config", None))
    if exit_code:
        raise SystemExit(exit_code)


def _generate(args: argparse.Namespace) -> None:
    prompt = _read_prompt(args.prompt, args.prompt_file)
    prompt = _augment_prompt(args, prompt)

    payload = {
        "model": args.model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "moderation": args.moderation,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    _force_image_stream(payload)

    output_format = _normalize_output_format(args.output_format)
    _validate_transparency(args.background, output_format)
    payload["output_format"] = output_format
    output_paths = _build_output_paths(args.out, output_format, args.n, args.out_dir)
    downscaled = None
    if args.downscale_max_dim is not None:
        downscaled = [str(_derive_downscale_path(p, args.downscale_suffix)) for p in output_paths]

    if args.dry_run:
        _print_request(
            {
                "base_url": args.api_config.base_url,
                "endpoint": "/v1/images/generations",
                "outputs": [str(p) for p in output_paths],
                "outputs_downscaled": downscaled,
                **payload,
            }
        )
        return

    if not args.quiet:
        print(
            "Calling Image API (generation). This can take up to a couple of minutes.",
            file=sys.stderr,
        )
    started = time.time()
    try:
        response_data = _post_json_api(
            args.api_config,
            "/images/generations",
            payload,
        )
        images = _extract_b64_images(response_data)
    except Exception as exc:
        _die_api_error(exc, args.api_config)
    elapsed = time.time() - started
    if not args.quiet:
        print(f"Generation completed in {elapsed:.1f}s.", file=sys.stderr)

    _decode_write_and_downscale(
        images,
        output_paths,
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
        output_format=output_format,
        quiet=args.quiet,
    )


def _edit(args: argparse.Namespace) -> None:
    prompt = _read_prompt(args.prompt, args.prompt_file)
    prompt = _augment_prompt(args, prompt)

    image_paths = _check_image_paths(args.image)
    mask_path = Path(args.mask) if args.mask else None
    if mask_path:
        if not mask_path.exists():
            _die(f"Mask file not found: {mask_path}")
        if mask_path.suffix.lower() != ".png":
            _warn(f"Mask should be a PNG with an alpha channel: {mask_path}")
        if mask_path.stat().st_size > MAX_IMAGE_BYTES:
            _warn(f"Mask exceeds 50MB limit: {mask_path}")

    payload = {
        "model": args.model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "input_fidelity": args.input_fidelity,
        "moderation": args.moderation,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    _force_image_stream(payload)

    output_format = _normalize_output_format(args.output_format)
    _validate_transparency(args.background, output_format)
    payload["output_format"] = output_format
    _validate_input_fidelity(args.input_fidelity)
    output_paths = _build_output_paths(args.out, output_format, args.n, args.out_dir)
    downscaled = None
    if args.downscale_max_dim is not None:
        downscaled = [str(_derive_downscale_path(p, args.downscale_suffix)) for p in output_paths]

    if args.dry_run:
        payload_preview = dict(payload)
        payload_preview["image"] = [str(p) for p in image_paths]
        if mask_path:
            payload_preview["mask"] = str(mask_path)
        _print_request(
            {
                "base_url": args.api_config.base_url,
                "endpoint": "/v1/images/edits",
                "outputs": [str(p) for p in output_paths],
                "outputs_downscaled": downscaled,
                **payload_preview,
            }
        )
        return

    if not args.quiet:
        print(
            f"Calling Image API (edit) with {len(image_paths)} image(s).",
            file=sys.stderr,
        )
    started = time.time()
    try:
        response_data = _post_edit_api(
            args.api_config,
            payload,
            image_paths,
            mask_path,
        )
        images = _extract_b64_images(response_data)
    except Exception as exc:
        _die_api_error(exc, args.api_config)

    elapsed = time.time() - started
    if not args.quiet:
        print(f"Edit completed in {elapsed:.1f}s.", file=sys.stderr)
    _decode_write_and_downscale(
        images,
        output_paths,
        force=args.force,
        downscale_max_dim=args.downscale_max_dim,
        downscale_suffix=args.downscale_suffix,
        output_format=output_format,
        quiet=args.quiet,
    )


def _open_files(paths: List[Path]):
    return _FileBundle(paths)


def _open_mask(mask_path: Optional[Path]):
    if mask_path is None:
        return _NullContext()
    return _SingleFile(mask_path)


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _SingleFile:
    def __init__(self, path: Path):
        self._path = path
        self._handle = None

    def __enter__(self):
        self._handle = self._path.open("rb")
        return self._handle

    def __exit__(self, exc_type, exc, tb):
        if self._handle:
            try:
                self._handle.close()
            except Exception:
                pass
        return False


class _FileBundle:
    def __init__(self, paths: List[Path]):
        self._paths = paths
        self._handles: List[object] = []

    def __enter__(self):
        self._handles = [p.open("rb") for p in self._paths]
        return self._handles

    def __exit__(self, exc_type, exc, tb):
        for handle in self._handles:
            try:
                handle.close()
            except Exception:
                pass
        return False


def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help=f"Path to JSON/TOML API config (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--model")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--n", type=int, default=1, help=f"Number of images to generate, 1-{MAX_IMAGES_PER_REQUEST}")
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", default=DEFAULT_QUALITY)
    parser.add_argument("--background")
    parser.add_argument("--output-format")
    parser.add_argument("--output-compression", type=int)
    parser.add_argument("--moderation")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--out-dir")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Suppress routine progress logs; errors are still printed")
    parser.add_argument("--augment", dest="augment", action="store_true")
    parser.add_argument("--no-augment", dest="augment", action="store_false")
    parser.set_defaults(augment=True)

    # Prompt augmentation hints
    parser.add_argument("--use-case")
    parser.add_argument("--scene")
    parser.add_argument("--subject")
    parser.add_argument("--style")
    parser.add_argument("--composition")
    parser.add_argument("--lighting")
    parser.add_argument("--palette")
    parser.add_argument("--materials")
    parser.add_argument("--text")
    parser.add_argument("--constraints")
    parser.add_argument("--negative")

    # Post-processing (optional): generate an additional downscaled copy for fast web loading.
    parser.add_argument("--downscale-max-dim", type=int)
    parser.add_argument("--downscale-suffix", default=DEFAULT_DOWNSCALE_SUFFIX)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CLI for image generation or editing via a configurable OpenAI-compatible Images API"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser("generate", help="Create a new image")
    _add_shared_args(gen_parser)
    gen_parser.add_argument(
        "--stream",
        action="store_true",
        help="Compatibility flag; image output requests always use event-stream output",
    )
    gen_parser.set_defaults(func=_generate)

    batch_parser = subparsers.add_parser(
        "generate-batch",
        help="Generate multiple prompts concurrently (JSONL input)",
    )
    _add_shared_args(batch_parser)
    batch_parser.add_argument("--input", required=True, help="Path to JSONL file (one job per line)")
    batch_parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    batch_parser.add_argument("--max-attempts", type=int, default=DEFAULT_BATCH_MAX_ATTEMPTS)
    batch_parser.add_argument(
        "--stream",
        action="store_true",
        help="Compatibility flag; image output requests always use event-stream output",
    )
    batch_parser.add_argument("--fail-fast", action="store_true")
    batch_parser.set_defaults(func=_generate_batch, out_dir=str(DEFAULT_BATCH_OUTPUT_DIR))

    edit_parser = subparsers.add_parser("edit", help="Edit an existing image")
    _add_shared_args(edit_parser)
    edit_parser.add_argument("--image", action="append", required=True)
    edit_parser.add_argument("--mask")
    edit_parser.add_argument("--input-fidelity")
    edit_parser.add_argument(
        "--stream",
        action="store_true",
        help="Compatibility flag; edit requests always use event-stream image output",
    )
    edit_parser.set_defaults(func=_edit)

    args = parser.parse_args()
    if args.n < 1 or args.n > MAX_IMAGES_PER_REQUEST:
        _die(f"--n must be between 1 and {MAX_IMAGES_PER_REQUEST}")
    if getattr(args, "concurrency", 1) < 1 or getattr(args, "concurrency", 1) > 25:
        _die("--concurrency must be between 1 and 25")
    if getattr(args, "max_attempts", 3) < 1 or getattr(args, "max_attempts", 3) > 10:
        _die("--max-attempts must be between 1 and 10")
    if args.output_compression is not None and not (0 <= args.output_compression <= 100):
        _die("--output-compression must be between 0 and 100")
    if getattr(args, "downscale_max_dim", None) is not None and args.downscale_max_dim < 1:
        _die("--downscale-max-dim must be >= 1")

    args.api_config = _resolve_api_config(
        config_path=args.config,
        dry_run=args.dry_run,
        default_model=args.model,
        quiet=args.quiet,
    )
    args.model = args.model or args.api_config.default_model

    _validate_model(args.model)
    _validate_size(args.size, args.model)
    _validate_quality(args.quality)
    _validate_background(args.background)
    _validate_model_specific_options(
        model=args.model,
        background=args.background,
        input_fidelity=getattr(args, "input_fidelity", None),
    )

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
