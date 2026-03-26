#!/usr/bin/env python3
"""
Find directories and files that look like UI components.

Uses heuristic signals rather than hardcoded paths. Works across frameworks
by looking for structural patterns common to component-based architectures.

Accepts framework context via --context flag (JSON string from detect-framework.py).
Outputs JSON with candidate component directories and their confidence scores.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from collections import Counter


# Directory names that strongly suggest components
COMPONENT_DIR_NAMES = {
    # High confidence
    "components", "ui", "atoms", "molecules", "organisms", "templates",
    "primitives", "elements", "widgets", "blocks", "partials",
    # Medium confidence
    "shared", "common", "core", "base", "design-system", "design_system",
    "ds", "kit", "library", "lib",
    # Framework-specific
    "views", "pages", "layouts", "sections", "features",
}

# Patterns in file content that suggest a component definition
COMPONENT_PATTERNS = {
    # React / Preact / Solid
    "react": [
        r"export\s+(?:default\s+)?function\s+\w+.*?(?:return|=>)\s*(?:\(?\s*<)",
        r"export\s+const\s+\w+\s*[:=]\s*(?:React\.)?(?:FC|FunctionComponent|memo|forwardRef)",
        r"export\s+default\s+class\s+\w+\s+extends\s+(?:React\.)?(?:Component|PureComponent)",
    ],
    # Vue
    "vue": [
        r"<template>",
        r"defineComponent\s*\(",
        r"<script\s+setup",
    ],
    # Svelte
    "svelte": [
        r"<script",  # all svelte files have script tags
    ],
    # Angular
    "angular": [
        r"@Component\s*\(",
        r"templateUrl\s*:",
        r"selector\s*:\s*['\"]",
    ],
    # Generic (works across frameworks)
    "generic": [
        r"export\s+(?:default\s+)?(?:function|const|class)\s+[A-Z]\w+",
    ],
}

# Files to skip
SKIP_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", ".svelte-kit", "dist",
    "build", "out", ".output", "__pycache__", ".cache", "coverage",
    ".turbo", ".vercel", ".netlify", "vendor", "public", "static",
    "assets", "images", "fonts", "storybook-static",
}

SKIP_FILE_PATTERNS = {
    ".test.", ".spec.", ".stories.", ".story.", ".mock.", ".fixture.",
    ".d.ts", ".min.", ".bundle.",
}


def is_component_file(file_path: Path, extensions: list[str]) -> bool:
    """Check if a file could be a component based on naming and content."""
    if file_path.suffix not in extensions:
        return False

    name = file_path.stem

    # Skip non-component patterns
    for skip in SKIP_FILE_PATTERNS:
        if skip in file_path.name:
            return False

    # Component files typically start with uppercase (PascalCase)
    # or are index files in a PascalCase directory
    if name[0].isupper():
        return True
    if name == "index" and file_path.parent.name[0:1].isupper():
        return True

    # Many component libraries use lowercase filenames (e.g., shadcn: button.tsx)
    # but export PascalCase components. Check file content as a fallback.
    try:
        content = file_path.read_text(errors="ignore")[:5000]
        # Look for PascalCase exports — strong signal of a component file
        if re.search(r"export\s+(?:default\s+)?(?:function|const|class)\s+[A-Z]\w+", content):
            return True
        # React.forwardRef with PascalCase assignment
        if re.search(r"(?:const|let)\s+[A-Z]\w+\s*=\s*(?:React\.)?forwardRef", content):
            return True
        # Named re-exports with PascalCase: export { Button, Card }
        # Use DOTALL to handle multi-line exports
        re_export = re.search(r"export\s*\{([^}]+)\}", content, re.DOTALL)
        if re_export:
            names = [n.strip().split(" as ")[-1].strip() for n in re_export.group(1).split(",")]
            if any(n and n[0].isupper() for n in names):
                return True
    except OSError:
        pass

    return False


def count_component_signals(dir_path: Path, extensions: list[str], framework: str) -> dict:
    """Count how many files in a directory look like components."""
    stats = {
        "total_files": 0,
        "component_files": 0,
        "pascal_case_files": 0,
        "index_exports": 0,
        "has_barrel_export": False,
        "sample_files": [],
        "depth": 0,
    }

    patterns = COMPONENT_PATTERNS.get(framework, []) + COMPONENT_PATTERNS["generic"]

    try:
        for item in dir_path.rglob("*"):
            # Track depth
            rel = item.relative_to(dir_path)
            depth = len(rel.parts) - 1
            stats["depth"] = max(stats["depth"], depth)

            if not item.is_file():
                continue
            if item.suffix not in extensions:
                continue
            if set(item.parts) & SKIP_DIRS:
                continue

            stats["total_files"] += 1

            if is_component_file(item, extensions):
                stats["component_files"] += 1
                if len(stats["sample_files"]) < 5:
                    stats["sample_files"].append(str(item.relative_to(dir_path)))

            if item.stem[0:1].isupper():
                stats["pascal_case_files"] += 1

            # Check for barrel export (index.ts that re-exports)
            if item.stem == "index" and item.parent == dir_path:
                try:
                    content = item.read_text(errors="ignore")[:2000]
                    if re.search(r"export\s+.*from\s+['\"]", content):
                        stats["has_barrel_export"] = True
                        stats["index_exports"] += content.count("export")
                except (OSError, UnicodeDecodeError):
                    pass

    except PermissionError:
        pass

    return stats


def score_directory(dir_path: Path, stats: dict, context: dict) -> float:
    """Score a directory on how likely it is to contain components."""
    score = 0.0
    reasons = []

    name = dir_path.name.lower()

    # Name-based scoring
    if name in {"components", "ui", "primitives", "elements", "atoms", "molecules"}:
        score += 40
        reasons.append(f"directory name '{name}' strongly suggests components")
    elif name in {"shared", "common", "core", "base", "lib", "kit"}:
        score += 20
        reasons.append(f"directory name '{name}' may contain components")
    elif name in {"design-system", "design_system", "ds"}:
        score += 35
        reasons.append(f"directory name '{name}' suggests design system")

    # Content-based scoring
    if stats["total_files"] == 0:
        return 0.0, reasons

    component_ratio = stats["component_files"] / max(stats["total_files"], 1)
    pascal_ratio = stats["pascal_case_files"] / max(stats["total_files"], 1)

    if component_ratio > 0.5:
        score += 30
        reasons.append(f"{stats['component_files']}/{stats['total_files']} files look like components")
    elif component_ratio > 0.25:
        score += 15
        reasons.append(f"{stats['component_files']}/{stats['total_files']} files look like components")

    if pascal_ratio > 0.5:
        score += 10
        reasons.append("majority PascalCase file names")

    if stats["has_barrel_export"]:
        score += 15
        reasons.append(f"barrel export with {stats['index_exports']} re-exports")

    # Penalize very deep directories (likely not a component root)
    if stats["depth"] > 4:
        score -= 10
        reasons.append("deeply nested (may not be component root)")

    # Penalize very few files
    if stats["total_files"] < 3:
        score -= 10
        reasons.append("very few files")

    # Bonus for being inside src/
    if "src" in dir_path.parts:
        score += 5

    return max(score, 0), reasons


def find_candidates(root: Path, context: dict) -> list[dict]:
    """Walk the directory tree and find component directory candidates."""
    extensions = context.get("component_extensions", [".tsx", ".jsx", ".vue", ".svelte"])
    framework = context.get("framework", "react")

    # Map framework IDs to pattern keys
    pattern_map = {
        "react": "react", "nextjs": "react", "gatsby": "react", "remix": "react",
        "vite-react": "react", "solid": "react", "preact": "react",
        "vue": "vue", "nuxt": "vue",
        "svelte": "svelte", "sveltekit": "svelte",
        "angular": "angular",
    }
    pattern_key = pattern_map.get(framework, "generic")

    candidates = []

    # Walk top-level directories (don't go too deep for the initial scan)
    search_roots = [root]
    if (root / "src").is_dir():
        search_roots.append(root / "src")
    if (root / "app").is_dir():
        search_roots.append(root / "app")
    if (root / "lib").is_dir():
        search_roots.append(root / "lib")
    if (root / "packages").is_dir():
        # Monorepo — check each package
        for pkg in (root / "packages").iterdir():
            if pkg.is_dir() and pkg.name not in SKIP_DIRS:
                search_roots.append(pkg)
                if (pkg / "src").is_dir():
                    search_roots.append(pkg / "src")

    seen = set()
    for search_root in search_roots:
        try:
            for item in search_root.iterdir():
                if not item.is_dir():
                    continue
                if item.name in SKIP_DIRS or item.name.startswith("."):
                    continue

                resolved = item.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)

                # Check this directory and its immediate children
                dirs_to_check = [item]
                try:
                    for child in item.iterdir():
                        if child.is_dir() and child.name not in SKIP_DIRS and not child.name.startswith("."):
                            child_resolved = child.resolve()
                            if child_resolved not in seen:
                                seen.add(child_resolved)
                                dirs_to_check.append(child)
                except PermissionError:
                    pass

                for check_dir in dirs_to_check:
                    stats = count_component_signals(check_dir, extensions, pattern_key)
                    score, reasons = score_directory(check_dir, stats, context)

                    if score > 15 or stats["component_files"] > 2:
                        rel_path = str(check_dir.relative_to(root))
                        candidates.append({
                            "path": rel_path,
                            "score": score,
                            "reasons": reasons,
                            "file_count": stats["total_files"],
                            "component_count": stats["component_files"],
                            "has_barrel_export": stats["has_barrel_export"],
                            "sample_files": stats["sample_files"],
                        })
        except PermissionError:
            pass

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=str, default="{}", help="Framework context JSON")
    parser.add_argument("--root", type=str, default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError:
        context = {}

    candidates = find_candidates(root, context)

    output = {
        "root": str(root),
        "candidates": candidates[:20],  # Top 20
        "total_found": len(candidates),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
