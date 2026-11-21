#!/usr/bin/env python3
"""Create a note inside an existing Obsidian vault without overwriting files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def safe_title(title: str) -> str:
    title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", title).strip(" .")
    title = re.sub(r"\s+", " ", title)
    if not title or title in {".", ".."}:
        raise ValueError("A nonempty note title is required")
    return title[:100].rstrip(" .")


def safe_folder(folder: str) -> Path:
    parts = Path(folder).parts
    if Path(folder).is_absolute() or any(p in {"..", "."} for p in parts):
        raise ValueError("Folder must be a relative path inside the vault")
    if any("\\" in p or "\x00" in p for p in parts):
        raise ValueError("Invalid folder path")
    return Path(*parts) if parts else Path("Research")


def write_note(vault: Path, folder: str, title: str, content: str) -> Path:
    vault = vault.expanduser().resolve(strict=True)
    if not vault.is_dir() or not (vault / ".obsidian").is_dir():
        raise ValueError("The target is not an existing Obsidian vault")
    target_dir = vault / safe_folder(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir = target_dir.resolve(strict=True)
    if not target_dir.is_relative_to(vault):
        raise ValueError("Folder resolves outside the vault")
    title = safe_title(title)
    data = (content.rstrip() + "\n").encode("utf-8")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".obsidian-research-", suffix=".tmp", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        for number in range(1, 1000):
            suffix = "" if number == 1 else f" ({number})"
            destination = target_dir / f"{title}{suffix}.md"
            try:
                os.link(temp_path, destination)
                return destination
            except FileExistsError:
                continue
        raise FileExistsError("Too many notes with the same title")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--folder", default="Research")
    parser.add_argument("--title", required=True)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    content = args.input.read_text(encoding="utf-8")
    if not content.strip():
        parser.error("Input note is empty")
    destination = write_note(args.vault, args.folder, args.title, content)
    print(json.dumps({"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
