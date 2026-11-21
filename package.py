#!/usr/bin/env python3
"""Build a reproducible ZIP with plugin.json at the archive root."""

import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "plugins" / "obsidian-research"
manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
version = manifest["version"]
output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / f"obsidian-research-{version}.zip"
output.parent.mkdir(parents=True, exist_ok=True)
files = [
    path for path in PLUGIN.rglob("*")
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    and "tests" not in path.relative_to(PLUGIN).parts
]
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
    for path in sorted(files):
        relative = path.relative_to(PLUGIN).as_posix()
        info = zipfile.ZipInfo(relative, date_time=(2026, 11, 21, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        package.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
print(output)
