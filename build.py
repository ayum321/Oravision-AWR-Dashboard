#!/usr/bin/env python3
"""
build.py — OraVision AWR Dashboard release packager
====================================================
Creates a clean, versioned zip containing only the files needed by end-users.
All _dev / audit / scratch files at the workspace root are excluded automatically.

Usage
-----
  python build.py                   # zip named  oravision-awr-vYYYYMMDD.zip
  python build.py --version 2.1.0   # custom version tag
  python build.py --dry-run         # print manifest without writing zip
  python build.py --out ./releases  # write zip to a specific folder

What is included
----------------
  backend/          FastAPI application (main.py, models/, routers/, services/, templates/, static/)
  requirements.txt  Python dependencies (from backend/requirements.txt)
  start.bat         One-click Windows launcher
  README.md         User guide (requirements + quick-start)
  ARCHITECTURE.md   Technical architecture reference

What is excluded
----------------
  __pycache__/, *.pyc          Compiled bytecode
  .env                         Secrets / local config
  tailwindcss.exe              Dev build tool
  backend/_*.py/txt/json       Internal debug & audit scripts in backend/
  Root _*.* files              All underscore-prefixed dev/audit files at workspace root
  *.zip, *.log, screenshot_*   Previous builds, logs, and screenshots
"""

import argparse
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DIST_NAME = "oravision-awr"
ZIP_PREFIX = f"{DIST_NAME}/"   # top-level folder name inside the zip


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

# Relative paths under backend/ that should NOT be shipped
_BACKEND_EXCLUDE_NAMES = {
    "tailwindcss.exe",
    ".env",
    "tailwind.config.js",
    "check_braces.py",
    "ingest_pdf.py",
    "test_v4.py",
}

_BACKEND_EXCLUDE_PREFIXES = ("_",)          # files starting with _ inside backend/ (but __init__.py is kept)
_BACKEND_EXCLUDE_EXTS    = {".pyc", ".log"}

_PYCACHE = "__pycache__"

# Root-level files/folders included in the zip
_ROOT_INCLUDES: list[tuple[str, str]] = [
    # (source relative to ROOT, archive name inside zip)
    ("start.bat",                          "start.bat"),
    ("README.md",                          "README.md"),
    ("docs/HIGH_LEVEL_ARCHITECTURE.md",    "ARCHITECTURE.md"),
    # backend/requirements.txt is used (not root requirements.txt which is Streamlit-based)
    ("backend/requirements.txt",           "requirements.txt"),
]


def _include_backend_file(path: Path) -> bool:
    """Return True if this backend/ file should be shipped."""
    parts = path.parts
    name  = path.name

    if _PYCACHE in parts:
        return False
    if path.suffix in _BACKEND_EXCLUDE_EXTS:
        return False
    if name in _BACKEND_EXCLUDE_NAMES:
        return False
    # Keep __init__.py (Python package marker) even though it starts with _
    if name != "__init__.py" and any(name.startswith(p) for p in _BACKEND_EXCLUDE_PREFIXES):
        return False
    return True


def collect_entries() -> list[tuple[Path, str]]:
    """Return list of (absolute_source, archive_path) for all release files."""
    entries: list[tuple[Path, str]] = []

    # 1. backend/ tree
    backend_dir = ROOT / "backend"
    for p in sorted(backend_dir.rglob("*")):
        if p.is_file() and _include_backend_file(p):
            arc = ZIP_PREFIX + p.relative_to(ROOT).as_posix()
            entries.append((p, arc))

    # 2. Root-level fixed files
    for rel, arc_name in _ROOT_INCLUDES:
        src = ROOT / Path(rel)
        if src.exists():
            entries.append((src, ZIP_PREFIX + arc_name))

    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _fmt_size(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1024:.1f} KB"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build OraVision AWR release zip",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        default=datetime.now().strftime("%Y%m%d"),
        help="Version tag appended to the zip name (default: today's date YYYYMMDD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the manifest without creating the zip",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT),
        help="Directory to write the zip into (default: project root)",
    )
    args = parser.parse_args()

    zip_name = f"{DIST_NAME}-v{args.version}.zip"
    zip_path = Path(args.out).resolve() / zip_name

    entries = collect_entries()

    # ── Print manifest ──────────────────────────────────────────────────────
    col = 62
    print(f"\nOraVision AWR  —  release build v{args.version}")
    print(f"Output : {zip_path}")
    print(f"\n{'Archive path':<{col}}  {'Size':>8}")
    print("─" * (col + 12))

    total_bytes = 0
    for src, arc in sorted(entries, key=lambda x: x[1]):
        sz = src.stat().st_size
        total_bytes += sz
        print(f"  {arc:<{col}}  {_fmt_size(sz):>8}")

    print("─" * (col + 12))
    print(f"  {'Total  (' + str(len(entries)) + ' files)':<{col}}  {_fmt_size(total_bytes):>8}\n")

    if args.dry_run:
        print("[dry-run]  Zip not created.")
        return

    # ── Write zip ────────────────────────────────────────────────────────────
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in entries:
            zf.write(src, arc)

    compressed = zip_path.stat().st_size
    ratio = (1 - compressed / max(total_bytes, 1)) * 100
    print(f"Created  {zip_path.name}")
    print(f"Size     {_fmt_size(compressed)} compressed  ({ratio:.0f}% reduction from {_fmt_size(total_bytes)} uncompressed)")
    print(f"\nDone. Ship {zip_path.name} to users — they double-click start.bat to launch.\n")


if __name__ == "__main__":
    main()
