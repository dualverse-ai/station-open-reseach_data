#!/usr/bin/env python3
"""Build a self-contained static site from the validated public archive."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_site"
FILES = ("index.html", "catalog.json", "README.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", ".nojekyll")
DIRECTORIES = ("assets", "images", "data")


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    for relative in FILES:
        source = ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, OUTPUT / relative)
    for relative in DIRECTORIES:
        source = ROOT / relative
        if not source.is_dir():
            raise FileNotFoundError(source)
        shutil.copytree(source, OUTPUT / relative, ignore=shutil.ignore_patterns("*.map"))
    files = [path for path in OUTPUT.rglob("*") if path.is_file()]
    size = sum(path.stat().st_size for path in files)
    print(f"Built {len(files)} files ({size / (1024 ** 2):.1f} MiB) in {OUTPUT}")


if __name__ == "__main__":
    main()
