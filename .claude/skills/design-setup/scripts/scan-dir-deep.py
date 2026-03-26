#!/usr/bin/env python3
"""
Deep-scan ONE directory for component/unit signals.

Called repeatedly during iterative discovery. Reports file metadata,
exported names, barrel exports, naming patterns, and sibling directories
so the prompt handler can decide whether to expand the search.

Usage:
  python3 scan-dir-deep.py --dir <path> [--extensions '.tsx,.svelte,.dart']
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    SKIP_DIRS, BARREL_FILES, should_skip,
    detect_name_case, extract_exported_names,
)

# Skip these file patterns
SKIP_FILE_PATTERNS = {
    ".test.", ".spec.", ".stories.", ".story.", ".mock.",
    ".fixture.", ".d.ts", ".min.", ".bundle.", ".generated.",
}


def analyze_file(file_path: Path) -> dict:
    """Analyze a single file for component signals."""
    name = file_path.stem
    result = {
        "name": file_path.name,
        "stem": name,
        "extension": file_path.suffix,
        "size_bytes": file_path.stat().st_size,
        "name_case": detect_name_case(name),
        "exported_names": [],
    }

    # Read content for export analysis
    try:
        content = file_path.read_text(errors="ignore")[:8000]
        result["exported_names"] = extract_exported_names(content)

        # For Svelte/Vue single-file components, the filename IS the component
        if file_path.suffix in {".svelte", ".vue"} and not result["exported_names"]:
            if name[0].isupper():
                result["exported_names"] = [name]
    except OSError:
        pass

    return result


def find_barrel_exports(dir_path: Path) -> dict:
    """Check for barrel/index files that re-export components."""
    for barrel_name in BARREL_FILES:
        barrel_path = dir_path / barrel_name
        if barrel_path.exists():
            try:
                content = barrel_path.read_text(errors="ignore")[:5000]
                names = extract_exported_names(content)
                return {
                    "file": barrel_name,
                    "exports": names,
                }
            except OSError:
                pass
    return {}


def scan_directory(dir_path: Path, extensions: set[str] | None = None) -> dict:
    """Deep-scan a single directory."""
    if not dir_path.is_dir():
        return {"error": f"Not a directory: {dir_path}"}

    files = []
    all_exported_names = []
    case_counts = Counter()

    for item in sorted(dir_path.iterdir()):
        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        if any(skip in item.name for skip in SKIP_FILE_PATTERNS):
            continue
        if extensions and item.suffix not in extensions:
            continue

        info = analyze_file(item)
        files.append(info)
        all_exported_names.extend(info["exported_names"])
        if info["name_case"] != "unknown":
            case_counts[info["name_case"]] += 1

    # Also scan immediate subdirectories (one level deep)
    subdirs = []
    for item in sorted(dir_path.iterdir()):
        if item.is_dir() and item.name not in SKIP_DIRS and not item.name.startswith("."):
            subdir_files = []
            for sub_item in item.iterdir():
                if sub_item.is_file() and not sub_item.name.startswith("."):
                    if not extensions or sub_item.suffix in extensions:
                        subdir_files.append(sub_item.name)

            subdirs.append({
                "name": item.name,
                "file_count": len(subdir_files),
                "sample_files": subdir_files[:5],
            })

    # Sibling directories (same parent)
    siblings = []
    parent = dir_path.parent
    for item in sorted(parent.iterdir()):
        if item.is_dir() and item != dir_path and item.name not in SKIP_DIRS and not item.name.startswith("."):
            siblings.append(item.name)

    # Barrel exports
    barrel = find_barrel_exports(dir_path)

    # Dominant naming pattern
    naming_pattern = case_counts.most_common(1)[0][0] if case_counts else "unknown"

    return {
        "directory": str(dir_path),
        "file_count": len(files),
        "files": files,
        "all_exported_names": sorted(set(all_exported_names)),
        "naming_pattern": naming_pattern,
        "barrel_export": barrel,
        "subdirectories": subdirs,
        "sibling_directories": siblings,
        "parent_directory": parent.name,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Directory to scan")
    parser.add_argument("--extensions", default=None,
                        help="Comma-separated extensions to include (e.g., '.tsx,.svelte')")
    args = parser.parse_args()

    dir_path = Path(args.dir).resolve()
    extensions = None
    if args.extensions:
        extensions = set(e.strip() for e in args.extensions.split(","))

    result = scan_directory(dir_path, extensions)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
