"""
Shared utilities for design-setup scripts.

Provides language-agnostic detection for:
- Name casing conventions
- Color literals (hex, rgb, hsl, oklch, Color(), UIColor)
- Size literals (px, rem, dp, sp, pt, em)
- Assignment patterns (CSS vars, SCSS vars, JS/TS/Dart/Swift constants)
- Spacing base computation (GCD of pixel values)
"""

import re
from math import gcd
from functools import reduce
from pathlib import Path

# Directories to skip during scanning
SKIP_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", ".svelte-kit", "dist",
    "build", ".output", "__pycache__", ".cache", "coverage",
    ".turbo", ".vercel", ".netlify", "vendor", "storybook-static",
    ".dart_tool", ".gradle", "Pods", "DerivedData", "target",
    ".idea", ".vscode", "__pycache__", ".mypy_cache", ".ruff_cache",
}

# Known config files that indicate ecosystem/project type
CONFIG_FILES = {
    # JS/TS ecosystem
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
    "tsconfig.json", "jsconfig.json",
    # Framework configs
    "next.config.js", "next.config.mjs", "next.config.ts",
    "nuxt.config.ts", "nuxt.config.js",
    "svelte.config.js", "svelte.config.ts",
    "astro.config.mjs", "astro.config.ts",
    "vite.config.ts", "vite.config.js", "vite.config.mjs",
    "angular.json", ".angular.json",
    "remix.config.js", "gatsby-config.js", "gatsby-config.ts",
    "ember-cli-build.js",
    # Styling
    "tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs",
    "postcss.config.js", "postcss.config.mjs", "postcss.config.ts",
    # Component libraries
    "components.json",  # shadcn/ui
    # Flutter/Dart
    "pubspec.yaml", "pubspec.lock",
    # iOS/Swift
    "Package.swift", "Podfile", "Podfile.lock",
    # Android/Kotlin
    "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
    # Rust
    "Cargo.toml", "Cargo.lock",
    # Python
    "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    # Ruby
    "Gemfile", "Gemfile.lock",
    # PHP
    "composer.json", "composer.lock",
    # Elixir
    "mix.exs",
    # Go
    "go.mod", "go.sum",
    # Monorepo
    "lerna.json", "nx.json", "turbo.json", "rush.json", "pnpm-workspace.yaml",
}

# File names that suggest token/value definitions
TOKEN_FILE_HINTS = {
    "token", "tokens", "theme", "themes", "variable", "variables",
    "color", "colors", "palette", "spacing", "typography", "constant",
    "constants", "design", "foundation", "foundations", "style", "styles",
    "primitives", "semantic",
}

# Barrel/index file names across languages
BARREL_FILES = {
    "index.ts", "index.tsx", "index.js", "index.jsx", "index.mjs",
    "index.dart", "mod.rs", "__init__.py", "index.svelte",
    "exports.ts", "exports.js",
}

# Notable directory names that suggest UI-related content
NOTABLE_DIR_NAMES = {
    # Component directories
    "components", "component", "ui", "atoms", "molecules", "organisms",
    "templates", "primitives", "elements", "widgets", "blocks", "partials",
    "shared", "common", "core", "base", "design-system", "design_system",
    "ds", "kit", "library", "lib", "design", "features",
    # Token/theme directories
    "theme", "themes", "tokens", "styles", "css", "scss", "sass",
    "foundations", "variables",
    # Page/view directories
    "pages", "views", "screens", "routes", "layouts", "sections",
    "app", "src",
}


def should_skip(path: Path) -> bool:
    """Check if a path contains a directory that should be skipped."""
    return bool(set(path.parts) & SKIP_DIRS)


def detect_name_case(name: str) -> str:
    """Detect the casing convention of a name (without extension)."""
    if not name:
        return "unknown"
    if "-" in name:
        return "kebab-case"
    if "_" in name:
        return "snake_case"
    if name[0].isupper() and any(c.islower() for c in name):
        return "PascalCase"
    if name[0].islower() and any(c.isupper() for c in name):
        return "camelCase"
    if name.islower():
        return "lowercase"
    if name.isupper():
        return "UPPERCASE"
    return "mixed"


# --- Color literal detection ---

COLOR_PATTERNS = [
    re.compile(r"#[0-9a-fA-F]{3,8}\b"),                          # Hex
    re.compile(r"rgba?\s*\([^)]+\)"),                              # rgb/rgba
    re.compile(r"hsla?\s*\([^)]+\)"),                              # hsl/hsla
    re.compile(r"oklch\s*\([^)]+\)"),                              # oklch (modern CSS)
    re.compile(r"oklab\s*\([^)]+\)"),                              # oklab
    re.compile(r"lch\s*\([^)]+\)"),                                # lch
    re.compile(r"lab\s*\([^)]+\)"),                                # lab
    re.compile(r"Color\s*\(\s*0x[0-9a-fA-F]+\s*\)"),              # Flutter Color(0xFF...)
    re.compile(r"Color\.fromARGB\s*\([^)]+\)"),                    # Flutter Color.fromARGB
    re.compile(r"Color\.fromRGBO\s*\([^)]+\)"),                    # Flutter Color.fromRGBO
    re.compile(r"UIColor\s*\([^)]+\)"),                            # iOS UIColor
    re.compile(r"Color\s*\(\s*red:\s*[\d.]+"),                     # SwiftUI Color(red:...)
    re.compile(r"Color\s*\(\s*\"[^\"]+\"\s*\)"),                   # SwiftUI Color("name")
    re.compile(r"Color\s*\.\s*[a-zA-Z]+"),                        # Color.blue, Color.primary
    re.compile(r"colorResource\s*\([^)]+\)"),                      # Android color resource
]


def is_color_value(value: str) -> bool:
    """Check if a string contains a color literal."""
    return any(p.search(value) for p in COLOR_PATTERNS)


def extract_color_literal(value: str) -> str | None:
    """Extract the first color literal from a value string."""
    for p in COLOR_PATTERNS:
        m = p.search(value)
        if m:
            return m.group()
    return None


# --- Size literal detection ---

SIZE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(px|rem|em|dp|sp|pt|vw|vh|rpx|lpx)\b"
)


def is_size_value(value: str) -> bool:
    """Check if a string contains a size/dimension literal."""
    return bool(SIZE_PATTERN.search(value))


def extract_size_literal(value: str) -> tuple[float, str] | None:
    """Extract the first size literal as (number, unit)."""
    m = SIZE_PATTERN.search(value)
    if m:
        return float(m.group(1)), m.group(2)
    return None


# --- Font detection ---

FONT_KEYWORDS = {
    "sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy",
    "ui-sans-serif", "ui-serif", "ui-monospace", "ui-rounded",
}

FONT_NAME_HINTS = {"font", "text", "type", "typo", "letter", "line-height"}


def is_font_value(name: str, value: str) -> bool:
    """Check if a name/value pair looks like a font/typography definition."""
    name_lower = name.lower()
    value_lower = value.lower()
    if any(h in name_lower for h in FONT_NAME_HINTS):
        return True
    if any(kw in value_lower for kw in FONT_KEYWORDS):
        return True
    return False


# --- Shadow detection ---

SHADOW_NAME_HINTS = {"shadow", "elevation", "depth"}


def is_shadow_value(name: str, value: str) -> bool:
    """Check if a name/value pair looks like a shadow definition."""
    name_lower = name.lower()
    if any(h in name_lower for h in SHADOW_NAME_HINTS):
        return True
    # CSS box-shadow pattern: has multiple numeric values with px
    if re.search(r"\d+px\s+\d+px", value):
        return True
    return False


# --- Radius detection ---

RADIUS_NAME_HINTS = {"radius", "rounded", "corner", "border-radius"}


def is_radius_value(name: str, value: str) -> bool:
    """Check if a name/value pair looks like a border-radius definition."""
    return any(h in name.lower() for h in RADIUS_NAME_HINTS)


# --- Assignment detection ---

ASSIGNMENT_PATTERNS = [
    # CSS custom properties: --name: value;
    re.compile(r"^\s*(--[\w-]+)\s*:\s*(.+?)\s*;?\s*$"),
    # SCSS/SASS variables: $name: value;
    re.compile(r"^\s*(\$[\w-]+)\s*:\s*(.+?)\s*;?\s*$"),
    # Less variables: @name: value;
    re.compile(r"^\s*(@[\w-]+)\s*:\s*(.+?)\s*;?\s*$"),
    # JS/TS const/let/var: const name = value
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([\w]+)\s*[:=]\s*['\"]?(.+?)['\"]?\s*[,;]?\s*$"),
    # Dart: static const name = value / final name = value
    re.compile(r"^\s*(?:static\s+)?(?:const|final)\s+\w+\s+([\w]+)\s*=\s*(.+?)\s*;?\s*$"),
    # Swift: static let name = value
    re.compile(r"^\s*(?:static\s+)?(?:let|var)\s+([\w]+)\s*[:=]\s*(.+?)\s*$"),
    # Object literal: name: value or "name": value
    re.compile(r"^\s*['\"]?([\w-]+)['\"]?\s*:\s*['\"]?(.+?)['\"]?\s*,?\s*$"),
    # Kotlin: val name = value
    re.compile(r"^\s*(?:const\s+)?val\s+([\w]+)\s*=\s*(.+?)\s*$"),
]


def extract_assignment(line: str) -> tuple[str, str] | None:
    """
    Extract a (name, value) pair from a line if it's an assignment.
    Returns None if the line isn't an assignment.
    """
    # Skip comments
    stripped = line.strip()
    if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return None
    if stripped.startswith("#") and not stripped.startswith("#["):  # Python/Ruby comment, not hex
        return None

    for pattern in ASSIGNMENT_PATTERNS:
        m = pattern.match(line)
        if m:
            name = m.group(1).strip()
            value = m.group(2).strip()
            # Filter out noise: very long values, import statements, function calls
            if len(value) > 200:
                continue
            if "import" in value or "require(" in value:
                continue
            return name, value

    return None


def categorize_value(name: str, value: str) -> str:
    """Categorize a named value into: color, size, font, shadow, radius, or other."""
    if is_color_value(value):
        return "color"
    if is_size_value(value):
        if is_radius_value(name, value):
            return "radius"
        return "size"
    if is_font_value(name, value):
        return "font"
    if is_shadow_value(name, value):
        return "shadow"
    if is_radius_value(name, value):
        return "radius"
    return "other"


# --- Spacing base computation ---

def compute_spacing_base(pixel_values: list[float]) -> int | None:
    """
    Compute the likely base spacing unit from a list of pixel values.
    Uses GCD to find the common factor.
    """
    # Filter to positive integers
    ints = [int(v) for v in pixel_values if v > 0 and v == int(v)]
    if len(ints) < 2:
        return None

    result = reduce(gcd, ints)
    if result < 2:
        return None
    return result


# --- Export detection ---

EXPORT_PATTERNS = [
    # JS/TS: export function/const/class Name
    re.compile(r"export\s+(?:default\s+)?(?:function|const|class)\s+([A-Z]\w+)"),
    # JS/TS: export { Name, Name2 }
    re.compile(r"export\s*\{([^}]+)\}", re.DOTALL),
    # Angular: @Component decorator
    re.compile(r"@Component\s*\("),
    # Flutter: class Name extends StatelessWidget/StatefulWidget/Widget
    re.compile(r"class\s+([A-Z]\w+)\s+extends\s+(?:Stateless|Stateful)?Widget"),
    # SwiftUI: struct Name: View
    re.compile(r"struct\s+([A-Z]\w+)\s*:\s*(?:some\s+)?View"),
    # Jetpack Compose: @Composable fun Name()
    re.compile(r"@Composable\s+fun\s+([A-Z]\w+)"),
    # React.forwardRef
    re.compile(r"(?:const|let)\s+([A-Z]\w+)\s*=\s*(?:React\.)?forwardRef"),
]


def extract_exported_names(content: str) -> list[str]:
    """Extract PascalCase exported/defined names from file content."""
    names = set()

    for pattern in EXPORT_PATTERNS:
        for match in pattern.finditer(content):
            text = match.group(1) if match.lastindex else match.group(0)

            # Handle export { Name1, Name2 } blocks
            if "{" in match.group(0):
                for part in text.split(","):
                    name = part.strip().split(" as ")[-1].strip()
                    if name and name[0].isupper():
                        names.add(name)
            elif text and text[0].isupper():
                names.add(text)

    # Also check for Svelte/Vue default exports (the filename IS the component name)
    # This is handled at the caller level, not here

    return sorted(names)
