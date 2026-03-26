#!/usr/bin/env python3
"""
Gather ecosystem signals from a repository.

This script COLLECTS FACTS, it does not make decisions. It reports:
- All config files found and what ecosystems they suggest
- All dependencies found and what libraries they indicate
- File extension counts (how many .ts, .tsx, .rs, .dart, etc.)
- TypeScript presence, monorepo signals, styling systems

The SKILL.md or prompt handler uses these facts to determine the
primary ecosystem. This avoids hardcoded priority logic that breaks
in polyglot monorepos.

Usage:
  python3 identify-ecosystem.py [--root <path>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from utils import SKIP_DIRS

# Config file → what it suggests (can suggest multiple things)
CONFIG_SIGNALS = {
    # JS/TS meta-frameworks
    "next.config.js":      {"ecosystem": "nextjs",    "name": "Next.js",     "lang": "typescript"},
    "next.config.mjs":     {"ecosystem": "nextjs",    "name": "Next.js",     "lang": "typescript"},
    "next.config.ts":      {"ecosystem": "nextjs",    "name": "Next.js",     "lang": "typescript"},
    "nuxt.config.ts":      {"ecosystem": "nuxt",      "name": "Nuxt",        "lang": "typescript"},
    "nuxt.config.js":      {"ecosystem": "nuxt",      "name": "Nuxt",        "lang": "javascript"},
    "svelte.config.js":    {"ecosystem": "sveltekit",  "name": "SvelteKit",  "lang": "typescript"},
    "svelte.config.ts":    {"ecosystem": "sveltekit",  "name": "SvelteKit",  "lang": "typescript"},
    "astro.config.mjs":    {"ecosystem": "astro",     "name": "Astro",       "lang": "typescript"},
    "astro.config.ts":     {"ecosystem": "astro",     "name": "Astro",       "lang": "typescript"},
    "angular.json":        {"ecosystem": "angular",   "name": "Angular",     "lang": "typescript"},
    ".angular.json":       {"ecosystem": "angular",   "name": "Angular",     "lang": "typescript"},
    "remix.config.js":     {"ecosystem": "remix",     "name": "Remix",       "lang": "typescript"},
    "gatsby-config.js":    {"ecosystem": "gatsby",    "name": "Gatsby",      "lang": "javascript"},
    "gatsby-config.ts":    {"ecosystem": "gatsby",    "name": "Gatsby",      "lang": "typescript"},
    "ember-cli-build.js":  {"ecosystem": "ember",     "name": "Ember",       "lang": "javascript"},
    "vite.config.ts":      {"ecosystem": "vite",      "name": "Vite",        "lang": "typescript"},
    "vite.config.js":      {"ecosystem": "vite",      "name": "Vite",        "lang": "javascript"},
    "vite.config.mjs":     {"ecosystem": "vite",      "name": "Vite",        "lang": "javascript"},
    # Styling
    "tailwind.config.js":  {"styling": "Tailwind CSS"},
    "tailwind.config.ts":  {"styling": "Tailwind CSS"},
    "tailwind.config.mjs": {"styling": "Tailwind CSS"},
    "postcss.config.js":   {"styling": "PostCSS"},
    "postcss.config.mjs":  {"styling": "PostCSS"},
    # Component library configs
    "components.json":     {"library": "shadcn/ui (possible)"},
    # Non-web ecosystems
    "pubspec.yaml":        {"ecosystem": "flutter",   "name": "Flutter",     "lang": "dart"},
    "Package.swift":       {"ecosystem": "swiftui",   "name": "Swift/SwiftUI", "lang": "swift"},
    "Podfile":             {"ecosystem": "ios",       "name": "iOS",         "lang": "swift"},
    "Cargo.toml":          {"ecosystem": "rust",      "name": "Rust",        "lang": "rust"},
    "go.mod":              {"ecosystem": "go",        "name": "Go",          "lang": "go"},
    "mix.exs":             {"ecosystem": "phoenix",   "name": "Phoenix",     "lang": "elixir"},
    "manage.py":           {"ecosystem": "django",    "name": "Django",      "lang": "python"},
    "artisan":             {"ecosystem": "laravel",   "name": "Laravel",     "lang": "php"},
    "Gemfile":             {"ecosystem": "rails",     "name": "Ruby",        "lang": "ruby"},
    # Package managers / signals
    "package.json":        {"signal": "Node.js/JavaScript ecosystem present"},
    "yarn.lock":           {"signal": "Yarn package manager"},
    "pnpm-lock.yaml":      {"signal": "pnpm package manager"},
    "package-lock.json":   {"signal": "npm package manager"},
    "bun.lockb":           {"signal": "Bun runtime"},
    "bun.lock":            {"signal": "Bun runtime"},
    "tsconfig.json":       {"signal": "TypeScript configured"},
    # Monorepo
    "pnpm-workspace.yaml": {"monorepo": "pnpm workspaces"},
    "lerna.json":          {"monorepo": "Lerna"},
    "nx.json":             {"monorepo": "Nx"},
    "turbo.json":          {"monorepo": "Turborepo"},
    "rush.json":           {"monorepo": "Rush"},
}

# Package.json dependency → what it indicates
DEPENDENCY_SIGNALS = {
    # Frameworks
    "react":            {"framework": "React"},
    "react-dom":        {"framework": "React"},
    "vue":              {"framework": "Vue"},
    "svelte":           {"framework": "Svelte"},
    "solid-js":         {"framework": "SolidJS"},
    "preact":           {"framework": "Preact"},
    "@angular/core":    {"framework": "Angular"},
    "lit":              {"framework": "Lit"},
    # Component libraries
    "primeng":          {"library": "PrimeNG"},
    "primevue":         {"library": "PrimeVue"},
    "primereact":       {"library": "PrimeReact"},
    "@radix-ui/react-slot": {"library": "Radix UI"},
    "@radix-ui/react-dialog": {"library": "Radix UI"},
    "@headlessui/react": {"library": "Headless UI"},
    "@headlessui/vue":  {"library": "Headless UI"},
    "@chakra-ui/react": {"library": "Chakra UI"},
    "@mantine/core":    {"library": "Mantine"},
    "@mui/material":    {"library": "Material UI"},
    "antd":             {"library": "Ant Design"},
    "vuetify":          {"library": "Vuetify"},
    "daisyui":          {"library": "DaisyUI"},
    "flowbite":         {"library": "Flowbite"},
    "@angular/material": {"library": "Angular Material"},
    "element-plus":     {"library": "Element Plus"},
    # Styling
    "tailwindcss":      {"styling": "Tailwind CSS"},
    "styled-components": {"styling": "styled-components"},
    "@emotion/react":   {"styling": "Emotion"},
    "sass":             {"styling": "Sass/SCSS"},
}


def count_extensions(root: Path, max_depth: int = 3) -> dict:
    """Count files by extension (quick scan, limited depth)."""
    counts = Counter()
    for dirpath_str, dirnames, filenames in root.walk():
        dirpath = Path(dirpath_str)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        depth = len(dirpath.relative_to(root).parts)
        if depth > max_depth:
            dirnames.clear()
            continue
        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext:
                counts[ext] += 1
    return dict(counts.most_common(20))


def read_package_deps(root: Path) -> dict:
    """Read dependencies from package.json."""
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        pkg = json.loads(pkg_path.read_text())
        deps = {}
        for key in ("dependencies", "devDependencies"):
            deps.update(pkg.get(key, {}))
        # Also check for workspaces
        if "workspaces" in pkg:
            deps["__has_workspaces__"] = True
        return deps
    except (json.JSONDecodeError, KeyError):
        return {}


def check_shadcn(root: Path) -> dict | None:
    """Check for shadcn/ui config."""
    cj_path = root / "components.json"
    if not cj_path.exists():
        return None
    try:
        cj = json.loads(cj_path.read_text())
        if "style" in cj or "tailwind" in cj or "aliases" in cj:
            return {
                "name": "shadcn/ui",
                "component_alias": cj.get("aliases", {}).get("components", ""),
            }
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def gather_signals(root: Path, config_files: list[str] | None = None) -> dict:
    """
    Gather ALL ecosystem signals without making decisions.
    Returns structured facts for the LLM to interpret.
    """
    if config_files is None:
        config_files = [f.name for f in root.iterdir() if f.is_file()]

    config_set = set(config_files)

    # Gather config file signals
    ecosystem_signals = []
    styling_signals = []
    library_signals = []
    monorepo_signals = []
    other_signals = []

    for filename in sorted(config_set):
        if filename in CONFIG_SIGNALS:
            signal = CONFIG_SIGNALS[filename]
            if "ecosystem" in signal:
                ecosystem_signals.append({
                    "config_file": filename,
                    "ecosystem": signal["ecosystem"],
                    "name": signal["name"],
                    "language": signal["lang"],
                })
            if "styling" in signal:
                styling_signals.append(signal["styling"])
            if "library" in signal:
                library_signals.append(signal["library"])
            if "monorepo" in signal:
                monorepo_signals.append(signal["monorepo"])
            if "signal" in signal:
                other_signals.append(signal["signal"])

    # Gather dependency signals
    pkg_deps = read_package_deps(root)
    frameworks_from_deps = []
    libraries_from_deps = []
    styling_from_deps = []
    has_workspaces = pkg_deps.pop("__has_workspaces__", False)

    if pkg_deps:
        seen = set()
        for dep, signal in DEPENDENCY_SIGNALS.items():
            if dep in pkg_deps:
                if "framework" in signal and signal["framework"] not in seen:
                    frameworks_from_deps.append(signal["framework"])
                    seen.add(signal["framework"])
                if "library" in signal and signal["library"] not in seen:
                    libraries_from_deps.append(signal["library"])
                    seen.add(signal["library"])
                if "styling" in signal and signal["styling"] not in seen:
                    styling_from_deps.append(signal["styling"])
                    seen.add(signal["styling"])

    # Check shadcn
    shadcn = check_shadcn(root)
    if shadcn:
        libraries_from_deps.append(shadcn["name"])

    # Count file extensions for context
    ext_counts = count_extensions(root)

    # TypeScript detection
    has_typescript = any(
        f.startswith("tsconfig") and f.endswith(".json") for f in config_set
    )

    # Monorepo
    if has_workspaces:
        monorepo_signals.append("package.json workspaces")

    return {
        "root": str(root),

        # All ecosystem candidates from config files (may be multiple!)
        "ecosystem_candidates": ecosystem_signals,

        # Frameworks detected from package.json dependencies
        "frameworks_from_deps": frameworks_from_deps,

        # Libraries
        "libraries": sorted(set(library_signals + libraries_from_deps)),

        # Styling systems
        "styling_systems": sorted(set(styling_signals + styling_from_deps)),

        # File extension counts (top 20) — helps judge which language dominates
        "file_extension_counts": ext_counts,

        # Signals
        "has_typescript": has_typescript,
        "has_package_json": "package.json" in config_set,
        "monorepo": monorepo_signals if monorepo_signals else None,
        "other_signals": other_signals,

        # Raw config files for reference
        "config_files_found": sorted(config_set & set(CONFIG_SIGNALS.keys())),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--configs", default=None, help="JSON array of config filenames")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    configs = json.loads(args.configs) if args.configs else None
    result = gather_signals(root, configs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
