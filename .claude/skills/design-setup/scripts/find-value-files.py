#!/usr/bin/env python3
"""
Find files likely to contain token/value definitions.

Thin finder using name heuristics and assignment density.
Returns candidates — use extract-named-values.py for deep analysis.

Usage:
  python3 find-value-files.py --root <path> [--extensions '.css,.scss,.ts,.dart']
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import SKIP_DIRS, TOKEN_FILE_HINTS, should_skip, extract_assignment


# Default extensions to scan for value files
DEFAULT_EXTENSIONS = {
    ".css", ".scss", ".sass", ".less",
    ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".dart", ".swift", ".kt", ".kts",
    ".json", ".yaml", ".yml",
    ".py", ".rb",
}


def score_filename(name: str) -> tuple[int, str]:
    """Score a filename based on how likely it is to contain token definitions."""
    stem = Path(name).stem.lower().strip("_")
    score = 0
    reason = ""

    for hint in TOKEN_FILE_HINTS:
        if hint in stem:
            score += 30
            reason = f"filename contains '{hint}'"
            break

    # Underscore prefix (SCSS partial convention: _variables.scss)
    if name.startswith("_"):
        score += 5

    # Global CSS files often contain tokens
    if stem in {"globals", "global", "app", "base", "root"}:
        score += 10
        reason = reason or f"common global file name '{stem}'"

    return score, reason


def check_assignment_density(file_path: Path, max_lines: int = 200) -> tuple[int, int]:
    """Count named assignments in the first N lines of a file."""
    try:
        content = file_path.read_text(errors="ignore")
        lines = content.splitlines()[:max_lines]
    except OSError:
        return 0, 0

    assignment_count = 0
    total_lines = len(lines)

    for line in lines:
        if extract_assignment(line):
            assignment_count += 1

    return assignment_count, total_lines


def find_candidates(root: Path, extensions: set[str]) -> list[dict]:
    """Find files that might contain token/value definitions."""
    candidates = []

    for dirpath_str, dirnames, filenames in root.walk():
        dirpath = Path(dirpath_str)

        # Prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        for filename in filenames:
            file_path = dirpath / filename

            if file_path.suffix.lower() not in extensions:
                continue
            if filename.startswith("."):
                continue
            if should_skip(file_path):
                continue

            # Skip test/story files
            if any(p in filename for p in [".test.", ".spec.", ".stories.", ".mock."]):
                continue

            name_score, name_reason = score_filename(filename)

            # Check assignment density for promising files or those with name hints
            assignment_count = 0
            total_lines = 0
            if name_score > 0 or file_path.suffix in {".css", ".scss", ".sass", ".less"}:
                assignment_count, total_lines = check_assignment_density(file_path)

            # High assignment density is a strong signal even without a good name
            density_score = 0
            density_reason = ""
            if total_lines > 0:
                density = assignment_count / total_lines
                if assignment_count >= 10:
                    density_score = 25
                    density_reason = f"{assignment_count} named assignments in {total_lines} lines"
                elif assignment_count >= 5:
                    density_score = 15
                    density_reason = f"{assignment_count} named assignments"

            total_score = name_score + density_score

            if total_score >= 15:
                rel_path = str(file_path.relative_to(root))
                reasons = [r for r in [name_reason, density_reason] if r]
                candidates.append({
                    "path": rel_path,
                    "score": total_score,
                    "reasons": reasons,
                    "assignment_count": assignment_count,
                    "extension": file_path.suffix,
                })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--extensions", default=None,
                        help="Comma-separated extensions (e.g., '.css,.scss,.ts')")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    extensions = DEFAULT_EXTENSIONS
    if args.extensions:
        extensions = set(e.strip() for e in args.extensions.split(","))

    candidates = find_candidates(root, extensions)

    output = {
        "root": str(root),
        "candidates": candidates[:20],
        "total_found": len(candidates),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
