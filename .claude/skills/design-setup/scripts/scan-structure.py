#!/usr/bin/env python3
"""
Map a repository's file tree — directories, extensions, config files.

Pure filesystem metadata. No file content is read. This gives the
prompt handler and Claude a structural overview to guide deeper scans.

Usage:
  python3 scan-structure.py [--root <path>] [--depth <n>] [--focus <subdir>]
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from utils import SKIP_DIRS, CONFIG_FILES, NOTABLE_DIR_NAMES, should_skip


def scan(root: Path, max_depth: int = 4, focus: str | None = None) -> dict:
    scan_root = root / focus if focus else root
    if not scan_root.is_dir():
        return {"error": f"Not a directory: {scan_root}"}

    ext_counts = Counter()
    dir_entries = []
    config_found = []
    notable_dirs = []
    total_files = 0

    # Find config files at project root
    for item in root.iterdir():
        if item.is_file() and item.name in CONFIG_FILES:
            config_found.append(item.name)

    # Walk the tree
    for dirpath_str, dirnames, filenames in scan_root.walk():
        dirpath = Path(dirpath_str)
        rel = dirpath.relative_to(scan_root)
        depth = len(rel.parts)

        # Prune skip dirs
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        if depth > max_depth:
            dirnames.clear()
            continue

        # Count files by extension in this directory
        dir_exts = Counter()
        for f in filenames:
            if f.startswith("."):
                continue
            ext = Path(f).suffix.lower()
            dir_exts[ext] += 1
            ext_counts[ext] += 1
            total_files += 1

        if dir_exts:
            dir_entry = {
                "path": str(rel) if str(rel) != "." else str(scan_root.relative_to(root)),
                "file_count": sum(dir_exts.values()),
                "extensions": dict(dir_exts.most_common()),
            }
            dir_entries.append(dir_entry)

        # Flag notable directories
        if dirpath.name.lower() in NOTABLE_DIR_NAMES:
            notable_dirs.append({
                "path": str(dirpath.relative_to(root)),
                "name": dirpath.name,
            })

    # Sort directories by file count descending
    dir_entries.sort(key=lambda d: d["file_count"], reverse=True)

    return {
        "root": str(root),
        "focus": focus,
        "total_files": total_files,
        "total_directories": len(dir_entries),
        "extension_counts": dict(ext_counts.most_common(20)),
        "directories": dir_entries[:40],
        "config_files": sorted(config_found),
        "notable_dirs": notable_dirs[:20],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--depth", type=int, default=4, help="Max directory depth")
    parser.add_argument("--focus", default=None, help="Subdirectory to focus on")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    result = scan(root, args.depth, args.focus)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
