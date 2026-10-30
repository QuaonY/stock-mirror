#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a distributable skill archive from an explicit file allowlist."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = (
    "SKILL.md",
    "README.md",
    "CHANGELOG.md",
    "index.html",
    "LICENSE",
)
PACKAGE_DIR_SUFFIXES: Dict[str, set[str]] = {
    "scripts": {".py"},
    "references": {".md"},
    "templates": {".md", ".csv"},
    "assets": {".jpg", ".png", ".svg"},
    "examples": {".html", ".json", ".md"},
}


def collect_package_files(root: Path = ROOT) -> List[Path]:
    """Return sorted package files, excluding local runtime state by construction."""
    files = [root / name for name in ROOT_FILES]
    for directory, suffixes in PACKAGE_DIR_SUFFIXES.items():
        base = root / directory
        if not base.is_dir():
            continue
        files.extend(
            path
            for path in base.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in suffixes
            and path.name != "package_skill.py"
            and "__pycache__" not in path.parts
        )

    state_dir = root / "state"
    if state_dir.is_dir():
        files.extend(
            path
            for path in state_dir.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and (path.name.endswith(".example.json") or path.name.endswith(".schema.json"))
        )

    missing = [path.relative_to(root).as_posix() for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required package file(s) missing: {', '.join(missing)}")
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def build_archive(output: Path, root: Path = ROOT) -> List[str]:
    files = collect_package_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    names = [path.relative_to(root).as_posix() for path in files]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in zip(files, names):
            archive.write(path, arcname=name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a StockMirror archive without tracked local account/runtime state"
    )
    parser.add_argument(
        "--output",
        default="dist/StockMirror.zip",
        help="archive destination (default: dist/StockMirror.zip)",
    )
    args = parser.parse_args()
    try:
        names = build_archive(Path(args.output))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "archive": str(Path(args.output)),
                "file_count": len(names),
                "files": names,
                "excluded": "state files other than *.example.json and *.schema.json",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
