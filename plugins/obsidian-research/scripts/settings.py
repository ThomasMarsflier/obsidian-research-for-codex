#!/usr/bin/env python3
"""Store per-vault research preferences and install the optional Obsidian style."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from write_note import safe_folder


DEFAULTS = {"language": "zh-CN", "folder": "Research", "max_images": 6}


def vault_path(path: Path) -> Path:
    vault = path.expanduser().resolve(strict=True)
    if not vault.is_dir() or not (vault / ".obsidian").is_dir():
        raise ValueError("The target is not an existing Obsidian vault")
    return vault


def atomic_json(path: Path, data: dict) -> None:
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".obsidian-research-", delete=False) as file:
            temp = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def read_settings(vault: Path) -> dict:
    path = vault / ".obsidian-research.json"
    settings = DEFAULTS.copy()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Settings file must contain a JSON object")
        settings.update(data)
    return settings


def configure(vault: Path, language: str, folder: str, max_images: int, install_style: bool = False) -> dict:
    vault = vault_path(vault)
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}", language):
        raise ValueError("Language must be a BCP-47 style tag such as zh-CN, en, or ja-JP")
    if not 0 <= max_images <= 10:
        raise ValueError("max_images must be between 0 and 10")
    safe_folder(folder)
    settings = read_settings(vault)
    settings.update({"language": language, "folder": folder, "max_images": max_images})
    atomic_json(vault / ".obsidian-research.json", settings)
    if install_style:
        source = Path(__file__).resolve().parents[1] / "assets" / "obsidian-research.css"
        obsidian = (vault / ".obsidian").resolve(strict=True)
        if not obsidian.is_relative_to(vault):
            raise ValueError("Obsidian settings resolve outside the vault")
        snippets = obsidian / "snippets"
        appearance_path = obsidian / "appearance.json"
        appearance = json.loads(appearance_path.read_text(encoding="utf-8")) if appearance_path.exists() else {}
        if not isinstance(appearance, dict):
            raise ValueError("Unexpected Obsidian appearance settings")
        enabled = appearance.get("enabledCssSnippets", [])
        if not isinstance(enabled, list):
            raise ValueError("Unexpected Obsidian appearance settings")
        snippets.mkdir(exist_ok=True)
        snippets = snippets.resolve(strict=True)
        if not snippets.is_relative_to(vault):
            raise ValueError("Snippet folder resolves outside the vault")
        destination = snippets / "obsidian-research.css"
        destination.write_bytes(source.read_bytes())
        if "obsidian-research" not in enabled:
            appearance["enabledCssSnippets"] = enabled + ["obsidian-research"]
            atomic_json(appearance_path, appearance)
    return settings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show")
    show.add_argument("--vault", required=True, type=Path)
    set_cmd = commands.add_parser("set")
    set_cmd.add_argument("--vault", required=True, type=Path)
    set_cmd.add_argument("--language", default="zh-CN")
    set_cmd.add_argument("--folder", default="Research")
    set_cmd.add_argument("--max-images", type=int, default=6)
    set_cmd.add_argument("--install-style", action="store_true")
    args = ap.parse_args()
    if args.command == "show":
        result = read_settings(vault_path(args.vault))
    else:
        result = configure(args.vault, args.language, args.folder, args.max_images, args.install_style)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
