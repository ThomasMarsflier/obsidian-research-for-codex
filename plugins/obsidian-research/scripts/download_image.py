#!/usr/bin/env python3
"""Save a permitted high-resolution image and its attribution beside Obsidian notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from crawl import USER_AGENT, SameHostRedirect, read_limited, robots_for, validate_url
from settings import atomic_json, vault_path
from write_note import safe_folder


MAX_IMAGE_BYTES = 15_000_000


def dimensions(data: bytes, mime: str) -> tuple[int, int]:
    if mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if mime == "image/jpeg" and data.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xff:
                offset += 1
                continue
            marker = data[offset + 1]
            if marker in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                return struct.unpack(">HH", data[offset + 5:offset + 9])[::-1]
            if marker in {0xd8, 0xd9} or 0xd0 <= marker <= 0xd7:
                offset += 2
                continue
            segment = struct.unpack(">H", data[offset + 2:offset + 4])[0]
            if segment < 2:
                break
            offset += 2 + segment
    if mime == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        kind = data[12:16]
        if kind == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
        if kind == b"VP8L" and data[20] == 0x2f:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1)
        if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return (int.from_bytes(data[26:28], "little") & 0x3fff, int.from_bytes(data[28:30], "little") & 0x3fff)
    raise ValueError("Unsupported or invalid PNG, JPEG, or WebP image")


def download_image(vault: Path, folder: str, url: str, source_page: str, license_name: str, credit: str, alt: str, min_pixels: int = 1_000_000) -> dict:
    vault = vault_path(vault)
    url = validate_url(url)
    source_page = validate_url(source_page)
    if not license_name.strip() or license_name.strip().lower() in {"unknown", "unspecified"}:
        raise ValueError("A verified reuse license or permission is required")
    host = urlsplit(url).hostname.lower().rstrip(".")
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    redirect = SameHostRedirect(host)
    opener = build_opener(redirect)
    redirect.robots = robots_for(opener, origin)
    if not redirect.robots.can_fetch(USER_AGENT, url):
        raise ValueError("Image URL blocked by robots.txt")
    with opener.open(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/jpeg,image/webp"}), timeout=20) as response:
        final_url = validate_url(response.geturl(), host)
        mime = response.headers.get_content_type()
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError(f"Unsupported content type: {mime}")
        data = read_limited(response, MAX_IMAGE_BYTES)
    width, height = dimensions(data, mime)
    if width * height < min_pixels or max(width, height) < 1200:
        raise ValueError(f"Image is below the requested high-resolution threshold: {width}x{height}")
    target_dir = vault / safe_folder(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir = target_dir.resolve(strict=True)
    if not target_dir.is_relative_to(vault):
        raise ValueError("Image folder resolves outside the vault")
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime]
    basename = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:16]
    destination = target_dir / f"{basename}{ext}"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".obsidian-research-image-", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(data).digest():
                raise FileExistsError("An image with this URL-derived name already exists with different content")
        else:
            os.link(temp_path, destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    metadata = {"url": final_url, "source_page": source_page, "license": license_name.strip(), "credit": credit.strip(), "alt": alt.strip(), "width": width, "height": height, "sha256": hashlib.sha256(data).hexdigest(), "downloaded_at": datetime.now(timezone.utc).isoformat()}
    atomic_json(destination.with_suffix(destination.suffix + ".json"), metadata)
    return {"path": str(destination), "wikilink": destination.relative_to(vault).as_posix(), **metadata}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--folder", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--source-page", required=True)
    ap.add_argument("--license", required=True)
    ap.add_argument("--credit", default="")
    ap.add_argument("--alt", default="")
    ap.add_argument("--min-pixels", type=int, default=1_000_000)
    args = ap.parse_args()
    if not 500_000 <= args.min_pixels <= 20_000_000:
        ap.error("min-pixels must be between 500,000 and 20,000,000")
    print(json.dumps(download_image(args.vault, args.folder, args.url, args.source_page, args.license, args.credit, args.alt, args.min_pixels), ensure_ascii=False))


if __name__ == "__main__":
    main()
