#!/usr/bin/env python3
"""Create the user-level ARC Image Gen configuration for Codex."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
from typing import Optional


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_TIMEOUT_SECONDS = 300.0


def _config_path() -> Path:
    raw_codex_home = os.getenv("CODEX_HOME")
    codex_home = Path(raw_codex_home).expanduser() if raw_codex_home else Path.home() / ".codex"
    return codex_home / "arc-imagegen" / "config.json"


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout_seconds must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("timeout_seconds must be greater than 0")
    return parsed


def _prompt_text(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_required_text(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} is required.", file=sys.stderr)


def _prompt_timeout(default: float) -> float:
    while True:
        value = input(f"timeout_seconds [{default:g}]: ").strip()
        if not value:
            return default
        try:
            return _positive_float(value)
        except argparse.ArgumentTypeError as exc:
            print(f"Invalid value: {exc}", file=sys.stderr)


def _prompt_secret() -> str:
    return getpass.getpass("api_key: ").strip()


def _confirm_overwrite(path: Path) -> bool:
    answer = input(f"Config already exists at {path}. Overwrite? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _coalesce_text(value: Optional[str], label: str, default: str, *, interactive: bool) -> str:
    if value is not None:
        return value.strip() or default
    if interactive:
        return _prompt_text(label, default)
    return default


def _coalesce_required_text(value: Optional[str], label: str, *, interactive: bool) -> str:
    if value is not None:
        return value.strip()
    if interactive:
        return _prompt_required_text(label)
    return ""


def _coalesce_timeout(value: Optional[float], *, interactive: bool) -> float:
    if value is not None:
        return value
    if interactive:
        return _prompt_timeout(DEFAULT_TIMEOUT_SECONDS)
    return DEFAULT_TIMEOUT_SECONDS


def _coalesce_api_key(value: Optional[str], *, interactive: bool) -> str:
    if value is not None:
        return value.strip()
    if interactive:
        return _prompt_secret()
    return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write ARC Image Gen config to the Codex user directory."
    )
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--default-model")
    parser.add_argument("--timeout-seconds", type=_positive_float)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target = _config_path()
    interactive = sys.stdin.isatty()

    if target.exists() and not args.force:
        if not interactive:
            print(f"Config already exists at {target}. Use --force to overwrite.", file=sys.stderr)
            return 1
        if not _confirm_overwrite(target):
            print(f"No changes written. Existing config kept at: {target}")
            return 0

    base_url = _coalesce_required_text(
        args.base_url,
        "base_url",
        interactive=interactive,
    )
    api_key = _coalesce_api_key(args.api_key, interactive=interactive)
    default_model = _coalesce_text(
        args.default_model,
        "default_model",
        DEFAULT_MODEL,
        interactive=interactive,
    )
    timeout_seconds = _coalesce_timeout(args.timeout_seconds, interactive=interactive)

    if not base_url:
        print("base_url is required. Re-run with --base-url or enter it at the prompt.", file=sys.stderr)
        return 1

    if not api_key:
        print("api_key is required. Re-run with --api-key or enter it at the prompt.", file=sys.stderr)
        return 1

    config = {
        "base_url": base_url,
        "api_key": api_key,
        "default_model": default_model,
        "timeout_seconds": timeout_seconds,
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote ARC Image Gen config to: {target}")
    print("base_url: [configured]")
    print(f"default_model: {default_model}")
    print(f"timeout_seconds: {timeout_seconds:g}")
    print("api_key: [configured]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
