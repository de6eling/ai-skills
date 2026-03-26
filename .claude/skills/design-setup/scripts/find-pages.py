#!/usr/bin/env python3
"""
Find page/view/route files — the places where components are composed.

These files are important for design-compose because they show how
components are currently used together. They serve as composition
pattern references.

Outputs JSON with candidate page files grouped by type.
"""

import argparse
import json
import re
import sys
from pathlib import Path


SKIP_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", "dist", "build",
    "out", ".output", "__pycache__", ".cache", "coverage",
    ".turbo", "storybook-static",
}

# Framework-specific page/route conventions
PAGE_CONVENTIONS = {
    "nextjs": {
        "dirs": ["app", "src/app", "pages", "src/pages"],
        "file_patterns": ["page.tsx", "page.jsx", "page.ts", "page.js",
                          "layout.tsx", "layout.jsx"],
        "description": "Next.js App Router and Pages Router",
    },
    "nuxt": {
        "dirs": ["pages", "src/pages"],
        "file_patterns": ["*.vue"],
        "description": "Nuxt pages directory",
    },
    "sveltekit": {
        "dirs": ["src/routes"],
        "file_patterns": ["+page.svelte", "+layout.svelte"],
        "description": "SvelteKit routes",
    },
    "remix": {
        "dirs": ["app/routes", "src/routes"],
        "file_patterns": ["*.tsx", "*.jsx"],
        "description": "Remix routes",
    },
    "gatsby": {
        "dirs": ["src/pages", "src/templates"],
        "file_patterns": ["*.tsx", "*.jsx"],
        "description": "Gatsby pages and templates",
    },
    "angular": {
        "dirs": ["src/app"],
        "file_patterns": ["*.component.ts"],
        "description": "Angular components (pages are components)",
    },
    "react": {
        "dirs": ["src/pages", "src/views", "src/screens", "src/routes",
                 "pages", "views", "screens", "app"],
        "file_patterns": ["*.tsx", "*.jsx"],
        "description": "React pages/views (convention-based)",
    },
    "vue": {
        "dirs": ["src/views", "src/pages", "views", "pages"],
        "file_patterns": ["*.vue"],
        "description": "Vue views/pages",
    },
}

# Generic page detection heuristics
GENERIC_PAGE_DIRS = [
    "pages", "views", "screens", "routes", "templates",
    "src/pages", "src/views", "src/screens", "src/routes",
    "app/routes", "app/pages",
]


def find_pages_by_convention(root: Path, framework: str, extensions: list[str]) -> list[dict]:
    """Find pages using framework-specific conventions."""
    pages = []
    convention = PAGE_CONVENTIONS.get(framework, PAGE_CONVENTIONS.get("react", {}))

    for dir_pattern in convention.get("dirs", []):
        dir_path = root / dir_pattern
        if not dir_path.is_dir():
            continue

        try:
            for file_path in dir_path.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix not in extensions:
                    continue
                if any(skip in str(file_path) for skip in SKIP_DIRS):
                    continue

                # Skip test/story files
                name = file_path.name
                if any(p in name for p in [".test.", ".spec.", ".stories.", ".story."]):
                    continue

                # Determine page type
                page_type = "page"
                if "layout" in name.lower():
                    page_type = "layout"
                elif "template" in name.lower():
                    page_type = "template"
                elif "error" in name.lower() or "404" in name or "not-found" in name.lower():
                    page_type = "error-page"
                elif "loading" in name.lower():
                    page_type = "loading-state"

                rel_path = str(file_path.relative_to(root))

                # Try to extract imports to understand component usage
                component_imports = extract_component_imports(file_path, extensions)

                pages.append({
                    "path": rel_path,
                    "page_type": page_type,
                    "component_imports": component_imports,
                    "source": convention.get("description", "convention"),
                })
        except (OSError, PermissionError):
            continue

    return pages


def find_pages_by_heuristic(root: Path, extensions: list[str]) -> list[dict]:
    """Find pages using generic heuristics when framework isn't detected."""
    pages = []
    seen = set()

    for dir_name in GENERIC_PAGE_DIRS:
        dir_path = root / dir_name
        if not dir_path.is_dir():
            continue

        try:
            for file_path in dir_path.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix not in extensions:
                    continue

                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)

                if any(skip in str(file_path) for skip in SKIP_DIRS):
                    continue

                name = file_path.name
                if any(p in name for p in [".test.", ".spec.", ".stories."]):
                    continue

                rel_path = str(file_path.relative_to(root))
                component_imports = extract_component_imports(file_path, extensions)

                pages.append({
                    "path": rel_path,
                    "page_type": "page",
                    "component_imports": component_imports,
                    "source": "heuristic (directory name)",
                })
        except (OSError, PermissionError):
            continue

    return pages


def extract_component_imports(file_path: Path, extensions: list[str]) -> list[str]:
    """Extract import statements that look like component imports."""
    try:
        content = file_path.read_text(errors="ignore")[:5000]
    except OSError:
        return []

    imports = []

    # ES module imports: import { Button, Card } from './components/ui'
    for match in re.finditer(r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]", content):
        names = [n.strip().split(" as ")[0].strip() for n in match.group(1).split(",")]
        source = match.group(2)

        for name in names:
            # Component imports are PascalCase
            if name and name[0].isupper():
                imports.append(name)

    # Default imports: import Button from './components/Button'
    for match in re.finditer(r"import\s+([A-Z]\w+)\s+from\s+['\"]([^'\"]+)['\"]", content):
        imports.append(match.group(1))

    return imports[:20]  # Cap at 20


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

    framework = context.get("framework", "")
    extensions = context.get("component_extensions", [".tsx", ".jsx", ".vue", ".svelte"])

    # Add common extensions
    all_extensions = set(extensions + [".ts", ".js"])

    # Try framework-specific detection first
    pages = find_pages_by_convention(root, framework, all_extensions)

    # Fall back to heuristic detection
    if not pages:
        pages = find_pages_by_heuristic(root, all_extensions)

    # Collect aggregate component usage stats
    component_usage = {}
    for page in pages:
        for comp in page.get("component_imports", []):
            component_usage[comp] = component_usage.get(comp, 0) + 1

    # Sort by most-used components
    top_components = sorted(component_usage.items(), key=lambda x: -x[1])[:30]

    output = {
        "root": str(root),
        "pages": pages[:50],
        "total_pages_found": len(pages),
        "component_usage_across_pages": dict(top_components),
        "most_composed_components": [c[0] for c in top_components[:10]],
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
