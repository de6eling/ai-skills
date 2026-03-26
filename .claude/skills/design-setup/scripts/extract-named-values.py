#!/usr/bin/env python3
"""
Analyze ONE file for named value assignments (tokens).

Extracts and categorizes named values: colors, sizes, fonts, shadows,
radii. Works across CSS, SCSS, JS/TS, Dart, Swift, JSON, etc.

Usage:
  python3 extract-named-values.py --file <path>
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    extract_assignment, categorize_value, extract_color_literal,
    extract_size_literal, compute_spacing_base,
)


def analyze_file(file_path: Path) -> dict:
    """Extract and categorize all named values from a file."""
    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}

    try:
        content = file_path.read_text(errors="ignore")
    except OSError as e:
        return {"error": str(e)}

    categories = {
        "color": {"count": 0, "samples": []},
        "size": {"count": 0, "samples": [], "pixel_values": []},
        "font": {"count": 0, "samples": []},
        "shadow": {"count": 0, "samples": []},
        "radius": {"count": 0, "samples": []},
        "other": {"count": 0, "samples": []},
    }

    total = 0

    for line in content.splitlines():
        assignment = extract_assignment(line)
        if not assignment:
            continue

        name, value = assignment
        category = categorize_value(name, value)
        total += 1

        cat = categories[category]
        cat["count"] += 1
        if len(cat["samples"]) < 3:
            cat["samples"].append(f"{name}: {value}")

        # Track pixel values for spacing base computation
        if category == "size":
            size = extract_size_literal(value)
            if size and size[1] == "px":
                cat["pixel_values"].append(size[0])

    # Compute spacing base
    spacing_base = None
    pixel_values = categories["size"].get("pixel_values", [])
    if pixel_values:
        spacing_base = compute_spacing_base(pixel_values)

    # Clean up pixel_values from output (internal use only)
    for cat in categories.values():
        cat.pop("pixel_values", None)

    # Remove empty categories
    categories = {k: v for k, v in categories.items() if v["count"] > 0}

    return {
        "file": str(file_path),
        "format": detect_format(file_path),
        "total_named_values": total,
        "categories": categories,
        "spacing_base_px": spacing_base,
    }


def detect_format(file_path: Path) -> str:
    """Detect the token format from file extension."""
    ext = file_path.suffix.lower()
    formats = {
        ".css": "css-custom-properties",
        ".scss": "scss-variables",
        ".sass": "sass-variables",
        ".less": "less-variables",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".dart": "dart",
        ".swift": "swift",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".py": "python",
    }
    return formats.get(ext, "unknown")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="File to analyze")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    result = analyze_file(file_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
