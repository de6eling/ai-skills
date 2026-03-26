#!/usr/bin/env python3
"""
Detect the web framework, language, and ecosystem of a repository.

This is the first script that runs during design-setup. Its output
informs all subsequent discovery scripts by telling them what patterns
to look for.

Outputs JSON to stdout with detected framework details.
"""

import json
import sys
from pathlib import Path


# Framework detection signals — ordered by specificity
# Each entry: (file_or_pattern, framework_id, framework_name, component_extension, styling_approach)
FRAMEWORK_SIGNALS = [
    # Meta-frameworks (check first — they imply the base framework)
    ("next.config.js", "nextjs", "Next.js", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("next.config.mjs", "nextjs", "Next.js", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("next.config.ts", "nextjs", "Next.js", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("nuxt.config.ts", "nuxt", "Nuxt", [".vue"], "scoped-css-or-tailwind"),
    ("nuxt.config.js", "nuxt", "Nuxt", [".vue"], "scoped-css-or-tailwind"),
    ("svelte.config.js", "sveltekit", "SvelteKit", [".svelte"], "scoped-css-or-tailwind"),
    ("svelte.config.ts", "sveltekit", "SvelteKit", [".svelte"], "scoped-css-or-tailwind"),
    ("astro.config.mjs", "astro", "Astro", [".astro", ".tsx", ".jsx"], "scoped-css-or-tailwind"),
    ("astro.config.ts", "astro", "Astro", [".astro", ".tsx", ".jsx"], "scoped-css-or-tailwind"),
    ("remix.config.js", "remix", "Remix", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("gatsby-config.js", "gatsby", "Gatsby", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("gatsby-config.ts", "gatsby", "Gatsby", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("angular.json", "angular", "Angular", [".ts"], "component-css"),
    (".angular.json", "angular", "Angular", [".ts"], "component-css"),
    ("ember-cli-build.js", "ember", "Ember", [".hbs", ".js", ".ts"], "component-css"),

    # Base frameworks
    ("vite.config.ts", "vite-react", "Vite + React", [".tsx", ".jsx"], "css-modules-or-tailwind"),
    ("vite.config.js", "vite-react", "Vite + React", [".tsx", ".jsx"], "css-modules-or-tailwind"),
]

# Package.json dependency signals (fallback detection)
DEPENDENCY_SIGNALS = {
    "react": ("react", "React", [".tsx", ".jsx"]),
    "react-dom": ("react", "React", [".tsx", ".jsx"]),
    "vue": ("vue", "Vue", [".vue"]),
    "svelte": ("svelte", "Svelte", [".svelte"]),
    "solid-js": ("solid", "SolidJS", [".tsx", ".jsx"]),
    "preact": ("preact", "Preact", [".tsx", ".jsx"]),
    "lit": ("lit", "Lit", [".ts", ".js"]),
    "@angular/core": ("angular", "Angular", [".ts"]),
}

# Styling system signals
STYLING_SIGNALS = [
    ("tailwind.config.js", "tailwind", "Tailwind CSS"),
    ("tailwind.config.ts", "tailwind", "Tailwind CSS"),
    ("tailwind.config.mjs", "tailwind", "Tailwind CSS"),
    ("postcss.config.js", "postcss", "PostCSS"),
    ("postcss.config.mjs", "postcss", "PostCSS"),
    ("styled-components", "styled-components", "styled-components"),  # package dep
    ("@emotion/react", "emotion", "Emotion"),  # package dep
    ("sass", "sass", "Sass/SCSS"),  # package dep
    ("less", "less", "Less"),  # package dep
]

# Component library signals (in package.json dependencies)
COMPONENT_LIBRARY_SIGNALS = {
    "@radix-ui/react-dialog": ("radix", "Radix UI"),
    "@radix-ui/react-slot": ("radix", "Radix UI"),
    "@headlessui/react": ("headlessui", "Headless UI"),
    "@headlessui/vue": ("headlessui", "Headless UI"),
    "@chakra-ui/react": ("chakra", "Chakra UI"),
    "@mantine/core": ("mantine", "Mantine"),
    "@mui/material": ("mui", "Material UI"),
    "antd": ("antd", "Ant Design"),
    "vuetify": ("vuetify", "Vuetify"),
    "@shadcn/ui": ("shadcn", "shadcn/ui"),
    "daisyui": ("daisyui", "DaisyUI"),
    "flowbite": ("flowbite", "Flowbite"),
    "primevue": ("primevue", "PrimeVue"),
    "primereact": ("primereact", "PrimeReact"),
    "element-plus": ("element-plus", "Element Plus"),
}

# TypeScript signals
TYPESCRIPT_SIGNALS = [
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.base.json",
]

# Monorepo signals
MONOREPO_SIGNALS = [
    ("pnpm-workspace.yaml", "pnpm"),
    ("lerna.json", "lerna"),
    ("nx.json", "nx"),
    ("turbo.json", "turborepo"),
    ("rush.json", "rush"),
]


def detect(root: Path) -> dict:
    result = {
        "root": str(root),
        "framework": None,
        "framework_name": None,
        "component_extensions": [],
        "styling_approach": None,
        "styling_systems": [],
        "component_libraries": [],
        "uses_typescript": False,
        "monorepo": None,
        "package_manager": None,
        "has_src_dir": False,
        "has_app_dir": False,
        "has_pages_dir": False,
        "confidence": "low",
        "clues": [],
    }

    # Check for src/, app/, pages/ directories
    result["has_src_dir"] = (root / "src").is_dir()
    result["has_app_dir"] = (root / "app").is_dir() or (root / "src" / "app").is_dir()
    result["has_pages_dir"] = (root / "pages").is_dir() or (root / "src" / "pages").is_dir()

    # Detect TypeScript
    for ts_file in TYPESCRIPT_SIGNALS:
        if (root / ts_file).exists():
            result["uses_typescript"] = True
            result["clues"].append(f"Found {ts_file}")
            break

    # Detect monorepo
    for mono_file, mono_type in MONOREPO_SIGNALS:
        if (root / mono_file).exists():
            result["monorepo"] = mono_type
            result["clues"].append(f"Monorepo detected: {mono_type} (found {mono_file})")
            break

    # Detect package manager
    if (root / "pnpm-lock.yaml").exists():
        result["package_manager"] = "pnpm"
    elif (root / "yarn.lock").exists():
        result["package_manager"] = "yarn"
    elif (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        result["package_manager"] = "bun"
    elif (root / "package-lock.json").exists():
        result["package_manager"] = "npm"

    # Detect framework from config files
    for config_file, fw_id, fw_name, extensions, styling in FRAMEWORK_SIGNALS:
        if (root / config_file).exists():
            result["framework"] = fw_id
            result["framework_name"] = fw_name
            result["component_extensions"] = extensions
            result["styling_approach"] = styling
            result["confidence"] = "high"
            result["clues"].append(f"Framework config found: {config_file}")
            break

    # Read package.json for dependency-based detection
    pkg_path = root / "package.json"
    all_deps = {}
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text())
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Fallback framework detection from dependencies
            if not result["framework"]:
                for dep, (fw_id, fw_name, extensions) in DEPENDENCY_SIGNALS.items():
                    if dep in all_deps:
                        result["framework"] = fw_id
                        result["framework_name"] = fw_name
                        result["component_extensions"] = extensions
                        result["confidence"] = "medium"
                        result["clues"].append(f"Framework inferred from dependency: {dep}")
                        break

            # Detect styling systems
            for signal_file, style_id, style_name in STYLING_SIGNALS:
                if (root / signal_file).exists():
                    result["styling_systems"].append({"id": style_id, "name": style_name})
                    result["clues"].append(f"Styling system: {style_name} (found {signal_file})")
                elif signal_file in all_deps:
                    result["styling_systems"].append({"id": style_id, "name": style_name})
                    result["clues"].append(f"Styling system: {style_name} (in dependencies)")

            # Detect component libraries
            for dep, (lib_id, lib_name) in COMPONENT_LIBRARY_SIGNALS.items():
                if dep in all_deps:
                    # Avoid duplicates
                    if not any(l["id"] == lib_id for l in result["component_libraries"]):
                        result["component_libraries"].append({"id": lib_id, "name": lib_name})
                        result["clues"].append(f"Component library: {lib_name}")

        except (json.JSONDecodeError, KeyError):
            result["clues"].append("package.json found but could not parse")

    # Check for shadcn/ui specifically (has a components.json config file)
    if (root / "components.json").exists():
        try:
            cj = json.loads((root / "components.json").read_text())
            if "style" in cj or "tailwind" in cj or "aliases" in cj:
                if not any(l["id"] == "shadcn" for l in result["component_libraries"]):
                    result["component_libraries"].append({"id": "shadcn", "name": "shadcn/ui"})
                    result["clues"].append("shadcn/ui detected (components.json)")
                    # shadcn tells us where components live
                    aliases = cj.get("aliases", {})
                    if "components" in aliases:
                        result["clues"].append(
                            f"shadcn component alias: {aliases['components']}"
                        )
        except (json.JSONDecodeError, KeyError):
            pass

    # Non-JS ecosystems fallback
    if not result["framework"]:
        # Django/Flask
        if (root / "manage.py").exists() or (root / "wsgi.py").exists():
            result["framework"] = "django"
            result["framework_name"] = "Django"
            result["component_extensions"] = [".html", ".jinja2"]
            result["confidence"] = "medium"
            result["clues"].append("Python web framework detected")
        # Rails
        elif (root / "Gemfile").exists() and (root / "app" / "views").is_dir():
            result["framework"] = "rails"
            result["framework_name"] = "Ruby on Rails"
            result["component_extensions"] = [".erb", ".haml", ".slim"]
            result["confidence"] = "medium"
            result["clues"].append("Rails detected")
        # Laravel
        elif (root / "artisan").exists():
            result["framework"] = "laravel"
            result["framework_name"] = "Laravel"
            result["component_extensions"] = [".blade.php", ".vue"]
            result["confidence"] = "medium"
            result["clues"].append("Laravel detected")
        # Phoenix/Elixir
        elif (root / "mix.exs").exists() and (root / "lib").is_dir():
            result["framework"] = "phoenix"
            result["framework_name"] = "Phoenix"
            result["component_extensions"] = [".heex", ".ex"]
            result["confidence"] = "medium"
            result["clues"].append("Phoenix/Elixir detected")

    return result


def main():
    root = Path.cwd()

    # Allow passing a directory argument
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()

    if not root.is_dir():
        print(json.dumps({"error": f"Not a directory: {root}"}))
        sys.exit(1)

    result = detect(root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
