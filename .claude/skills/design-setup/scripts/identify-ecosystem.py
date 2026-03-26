#!/usr/bin/env python3
"""
Identify the project ecosystem, language, and tooling from config files.

Takes config file list (from scan-structure) or scans the root directly.
Covers web and non-web ecosystems.

Usage:
  python3 identify-ecosystem.py [--root <path>] [--configs '["package.json","svelte.config.js"]']
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import should_skip

# Config file → ecosystem hypothesis
# Ordered by specificity (meta-frameworks first, then base frameworks)
ECOSYSTEM_SIGNALS = [
    # JS/TS Meta-frameworks
    ("next.config.js",      "nextjs",     "Next.js",     "typescript", [".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("next.config.mjs",     "nextjs",     "Next.js",     "typescript", [".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("next.config.ts",      "nextjs",     "Next.js",     "typescript", [".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("nuxt.config.ts",      "nuxt",       "Nuxt",        "typescript", [".vue"],         [".css", ".scss", ".ts", ".json"]),
    ("nuxt.config.js",      "nuxt",       "Nuxt",        "javascript", [".vue"],         [".css", ".scss", ".js", ".json"]),
    ("svelte.config.js",    "sveltekit",  "SvelteKit",   "typescript", [".svelte"],      [".css", ".scss", ".ts", ".json"]),
    ("svelte.config.ts",    "sveltekit",  "SvelteKit",   "typescript", [".svelte"],      [".css", ".scss", ".ts", ".json"]),
    ("astro.config.mjs",    "astro",      "Astro",       "typescript", [".astro", ".tsx", ".jsx", ".svelte", ".vue"], [".css", ".scss", ".ts", ".json"]),
    ("astro.config.ts",     "astro",      "Astro",       "typescript", [".astro", ".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("angular.json",        "angular",    "Angular",     "typescript", [".ts"],          [".css", ".scss", ".ts", ".json"]),
    (".angular.json",       "angular",    "Angular",     "typescript", [".ts"],          [".css", ".scss", ".ts", ".json"]),
    ("remix.config.js",     "remix",      "Remix",       "typescript", [".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("gatsby-config.js",    "gatsby",     "Gatsby",      "javascript", [".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("gatsby-config.ts",    "gatsby",     "Gatsby",      "typescript", [".tsx", ".jsx"], [".css", ".scss", ".ts", ".json"]),
    ("ember-cli-build.js",  "ember",      "Ember",       "javascript", [".hbs", ".js", ".ts"], [".css", ".scss", ".js"]),
    ("vite.config.ts",      "vite",       "Vite",        "typescript", [".tsx", ".jsx", ".vue", ".svelte"], [".css", ".scss", ".ts", ".json"]),
    ("vite.config.js",      "vite",       "Vite",        "javascript", [".tsx", ".jsx", ".vue", ".svelte"], [".css", ".scss", ".js", ".json"]),
    ("vite.config.mjs",     "vite",       "Vite",        "javascript", [".tsx", ".jsx", ".vue", ".svelte"], [".css", ".scss", ".js", ".json"]),

    # Non-web ecosystems
    ("pubspec.yaml",        "flutter",    "Flutter",     "dart",       [".dart"],        [".dart", ".yaml", ".json"]),
    ("Package.swift",       "swiftui",    "Swift/SwiftUI", "swift",   [".swift"],       [".swift", ".xcassets"]),
    ("Podfile",             "ios",        "iOS",         "swift",      [".swift", ".m"], [".swift", ".plist"]),

    # Python web
    ("manage.py",           "django",     "Django",      "python",     [".html", ".py"], [".css", ".scss", ".py", ".json"]),

    # Ruby
    ("Gemfile",             "rails",      "Ruby on Rails", "ruby",    [".erb", ".haml"], [".css", ".scss", ".rb"]),

    # PHP
    ("artisan",             "laravel",    "Laravel",     "php",        [".blade.php", ".vue"], [".css", ".scss", ".php"]),

    # Elixir
    ("mix.exs",             "phoenix",    "Phoenix",     "elixir",     [".heex", ".ex"], [".css", ".ex"]),

    # Rust web (Leptos, Yew, Dioxus)
    ("Cargo.toml",          "rust",       "Rust",        "rust",       [".rs"],          [".rs", ".css", ".json"]),

    # Go
    ("go.mod",              "go",         "Go",          "go",         [".go", ".templ"], [".css", ".go"]),
]

# Package dependency → (ecosystem_refinement, library_name)
DEPENDENCY_SIGNALS = {
    # JS/TS base frameworks (for Vite detection refinement)
    "react":            ("react",    "React"),
    "react-dom":        ("react",    "React"),
    "vue":              ("vue",      "Vue"),
    "svelte":           ("svelte",   "Svelte"),
    "solid-js":         ("solid",    "SolidJS"),
    "preact":           ("preact",   "Preact"),
    "@angular/core":    ("angular",  "Angular"),
    "lit":              ("lit",      "Lit"),
    # Component libraries
    "primeng":          (None, "PrimeNG"),
    "primevue":         (None, "PrimeVue"),
    "primereact":       (None, "PrimeReact"),
    "@radix-ui/react-slot": (None, "Radix UI"),
    "@radix-ui/react-dialog": (None, "Radix UI"),
    "@headlessui/react": (None, "Headless UI"),
    "@headlessui/vue":  (None, "Headless UI"),
    "@chakra-ui/react": (None, "Chakra UI"),
    "@mantine/core":    (None, "Mantine"),
    "@mui/material":    (None, "Material UI"),
    "antd":             (None, "Ant Design"),
    "vuetify":          (None, "Vuetify"),
    "daisyui":          (None, "DaisyUI"),
    "flowbite":         (None, "Flowbite"),
    "@angular/material": (None, "Angular Material"),
    "element-plus":     (None, "Element Plus"),
    # Styling
    "tailwindcss":      (None, "Tailwind CSS"),
    "styled-components": (None, "styled-components"),
    "@emotion/react":   (None, "Emotion"),
    "sass":             (None, "Sass/SCSS"),
}

# Flutter dependency signals (pubspec.yaml)
FLUTTER_DEPENDENCY_SIGNALS = {
    "flutter":          (None, "Flutter SDK"),
    "cupertino_icons":  (None, "Cupertino Icons"),
    "material_design_icons_flutter": (None, "Material Icons"),
}


def read_package_deps(root: Path) -> dict:
    """Read dependencies from package.json."""
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        pkg = json.loads(pkg_path.read_text())
        return {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    except (json.JSONDecodeError, KeyError):
        return {}


def read_pubspec_deps(root: Path) -> dict:
    """Read dependencies from pubspec.yaml (basic YAML parsing without pyyaml)."""
    pubspec_path = root / "pubspec.yaml"
    if not pubspec_path.exists():
        return {}
    try:
        content = pubspec_path.read_text()
        deps = {}
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in ("dependencies:", "dev_dependencies:"):
                in_deps = True
                continue
            if in_deps and line and not line[0].isspace():
                in_deps = False
                continue
            if in_deps and ":" in stripped:
                name = stripped.split(":")[0].strip()
                if name and not name.startswith("#"):
                    deps[name] = True
        return deps
    except OSError:
        return {}


def check_shadcn(root: Path) -> dict | None:
    """Check for shadcn/ui config (components.json)."""
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


def check_android(root: Path) -> bool:
    """Check if a Gradle project is Android (not just any JVM project)."""
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        path = root / gradle_file
        if path.exists():
            try:
                content = path.read_text()[:2000]
                if "android" in content.lower() or "com.android" in content:
                    return True
            except OSError:
                pass
    return False


def identify(root: Path, config_files: list[str] | None = None) -> dict:
    """Identify the project ecosystem from config files and dependencies."""
    if config_files is None:
        config_files = [f.name for f in root.iterdir() if f.is_file()]

    config_set = set(config_files)

    result = {
        "root": str(root),
        "ecosystem": None,
        "ecosystem_name": None,
        "language": None,
        "ui_file_extensions": [],
        "value_file_extensions": [],
        "confidence": "low",
        "signals": [],
        "known_libraries": [],
        "styling_systems": [],
        "uses_typescript": "tsconfig.json" in config_set or "tsconfig.app.json" in config_set,
        "monorepo": None,
    }

    # Detect ecosystem from config files
    for config_file, eco_id, eco_name, lang, ui_exts, val_exts in ECOSYSTEM_SIGNALS:
        if config_file in config_set:
            result["ecosystem"] = eco_id
            result["ecosystem_name"] = eco_name
            result["language"] = lang
            result["ui_file_extensions"] = ui_exts
            result["value_file_extensions"] = val_exts
            result["confidence"] = "high"
            result["signals"].append(f"Config file: {config_file}")
            break

    # Special case: Android with Gradle
    if result["ecosystem"] is None and ("build.gradle" in config_set or "build.gradle.kts" in config_set):
        if check_android(root):
            result["ecosystem"] = "android"
            result["ecosystem_name"] = "Android"
            result["language"] = "kotlin"
            result["ui_file_extensions"] = [".kt", ".xml"]
            result["value_file_extensions"] = [".kt", ".xml", ".json"]
            result["confidence"] = "high"
            result["signals"].append("Android Gradle project")

    # Refine with package.json dependencies
    pkg_deps = read_package_deps(root)
    if pkg_deps:
        seen_libs = set()
        for dep, (refinement, lib_name) in DEPENDENCY_SIGNALS.items():
            if dep in pkg_deps:
                if lib_name not in seen_libs:
                    if refinement:
                        # Refine ecosystem (e.g., Vite → Vite + React)
                        if result["ecosystem"] == "vite":
                            result["ecosystem"] = f"vite-{refinement}"
                            result["ecosystem_name"] = f"Vite + {lib_name}"
                            result["signals"].append(f"Framework: {lib_name} (from deps)")
                        elif result["ecosystem"] is None:
                            result["ecosystem"] = refinement
                            result["ecosystem_name"] = lib_name
                            result["language"] = "typescript" if result["uses_typescript"] else "javascript"
                            result["confidence"] = "medium"
                            result["signals"].append(f"Framework: {lib_name} (from deps)")
                    else:
                        # It's a library, not a framework refinement
                        if lib_name in ("Tailwind CSS", "Sass/SCSS", "styled-components", "Emotion"):
                            result["styling_systems"].append(lib_name)
                            result["signals"].append(f"Styling: {lib_name}")
                        else:
                            result["known_libraries"].append(lib_name)
                            result["signals"].append(f"Library: {lib_name}")
                    seen_libs.add(lib_name)

    # Check for shadcn/ui
    shadcn = check_shadcn(root)
    if shadcn:
        result["known_libraries"].append(shadcn["name"])
        result["signals"].append(f"shadcn/ui detected (components.json)")
        if shadcn["component_alias"]:
            result["signals"].append(f"shadcn component alias: {shadcn['component_alias']}")

    # Refine with pubspec.yaml dependencies
    pubspec_deps = read_pubspec_deps(root)
    if pubspec_deps:
        for dep, (_, lib_name) in FLUTTER_DEPENDENCY_SIGNALS.items():
            if dep in pubspec_deps:
                result["known_libraries"].append(lib_name)

    # Monorepo detection
    monorepo_signals = {
        "pnpm-workspace.yaml": "pnpm",
        "lerna.json": "lerna",
        "nx.json": "nx",
        "turbo.json": "turborepo",
        "rush.json": "rush",
    }
    for mono_file, mono_type in monorepo_signals.items():
        if mono_file in config_set:
            result["monorepo"] = mono_type
            result["signals"].append(f"Monorepo: {mono_type}")
            break

    # TypeScript signal
    if result["uses_typescript"]:
        result["signals"].append("TypeScript detected")
        if result["language"] == "javascript":
            result["language"] = "typescript"

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--configs", default=None, help="JSON array of config filenames")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    configs = json.loads(args.configs) if args.configs else None
    result = identify(root, configs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
