#!/usr/bin/env python3
"""
Find files that import or use specific named components.

Given component names, searches the repo for files that reference them.
Language-agnostic: looks for import/require/use patterns and name usage.

Usage:
  python3 find-importers.py --root <path> --names '["Button","Card"]' [--extensions '.tsx,.svelte']
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import SKIP_DIRS, should_skip

# Skip patterns for files we don't want to report as "composition" files
SKIP_FILE_PATTERNS = {".test.", ".spec.", ".stories.", ".story.", ".mock.", ".d.ts"}

# Default extensions to search
DEFAULT_EXTENSIONS = {
    ".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro",
    ".dart", ".swift", ".kt", ".html", ".erb", ".heex",
    ".py", ".rb", ".php",
}


def find_references(root: Path, names: list[str], extensions: set[str]) -> dict:
    """Find files that reference the given names via imports or usage."""
    # Build regex for each name
    name_patterns = {}
    for name in names:
        # Match the name in import statements or as a used identifier
        # This catches: import { Name }, <Name, Name(, Name., etc.
        name_patterns[name] = re.compile(
            r"(?:"
            r"import\s+.*?" + re.escape(name) + r"|"  # import ... Name
            r"from\s+.*?" + re.escape(name) + r"|"     # from 'path/Name'
            r"<" + re.escape(name) + r"[\s/>]|"         # <Name or <Name>
            r"\b" + re.escape(name) + r"\s*\(|"         # Name( — function call
            r"\b" + re.escape(name) + r"\s*\{|"         # Name{ — Kotlin/Swift
            r"@" + re.escape(name) + r"\b"              # @Name — decorator
            r")"
        )

    # Track results per name
    results = {name: [] for name in names}
    file_component_map = {}  # file -> set of components used

    for dirpath_str, dirnames, filenames in root.walk():
        dirpath = Path(dirpath_str)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        for filename in filenames:
            file_path = dirpath / filename

            if file_path.suffix not in extensions:
                continue
            if any(skip in filename for skip in SKIP_FILE_PATTERNS):
                continue
            if should_skip(file_path):
                continue

            try:
                content = file_path.read_text(errors="ignore")[:10000]
            except OSError:
                continue

            rel_path = str(file_path.relative_to(root))
            found_in_file = set()

            for name, pattern in name_patterns.items():
                if pattern.search(content):
                    results[name].append(rel_path)
                    found_in_file.add(name)

            if len(found_in_file) > 1:
                file_component_map[rel_path] = sorted(found_in_file)

    # Build summary
    composition_files = sorted(
        file_component_map.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )

    return {
        "root": str(root),
        "references": {name: sorted(files) for name, files in results.items()},
        "composition_files": [
            {"file": f, "components_used": comps}
            for f, comps in composition_files
        ][:20],
        "top_composed_in": [f for f, _ in composition_files[:5]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--names", required=True, help="JSON array of component names")
    parser.add_argument("--extensions", default=None,
                        help="Comma-separated extensions")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    names = json.loads(args.names)
    extensions = DEFAULT_EXTENSIONS
    if args.extensions:
        extensions = set(e.strip() for e in args.extensions.split(","))

    result = find_references(root, names, extensions)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
