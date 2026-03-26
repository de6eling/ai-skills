#!/usr/bin/env python3
"""
Find design token files — colors, spacing, typography, shadows, etc.

Searches for token definitions across different approaches:
- CSS custom properties (--color-*, --space-*, etc.)
- Tailwind config (theme.extend.colors, etc.)
- JavaScript/TypeScript theme objects
- SCSS/SASS variables
- JSON/YAML token files (Style Dictionary, Tokens Studio, etc.)
- Design system config files (chakra theme, mantine theme, etc.)

Outputs JSON with found token sources and extracted token samples.
"""

import argparse
import json
import re
import sys
from pathlib import Path


SKIP_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", "dist", "build",
    "out", ".output", "__pycache__", ".cache", "coverage",
    ".turbo", "public", "storybook-static",
}

# File patterns that commonly contain tokens
TOKEN_FILE_PATTERNS = [
    # CSS custom properties
    ("**/*.css", "css-variables"),
    # Tailwind config
    ("tailwind.config.*", "tailwind-config"),
    # Theme files
    ("**/theme.*", "theme-file"),
    ("**/theme/**", "theme-directory"),
    ("**/themes/**", "theme-directory"),
    # Token files
    ("**/tokens.*", "token-file"),
    ("**/tokens/**", "token-directory"),
    ("**/design-tokens/**", "token-directory"),
    # Variables / constants
    ("**/variables.*", "variables-file"),
    ("**/vars.*", "variables-file"),
    ("**/constants.*", "constants-file"),
    # Style Dictionary
    ("**/style-dictionary/**", "style-dictionary"),
    ("**/*.tokens.json", "token-json"),
    # SCSS variables
    ("**/_variables.scss", "scss-variables"),
    ("**/_colors.scss", "scss-variables"),
    ("**/_spacing.scss", "scss-variables"),
    ("**/_typography.scss", "scss-variables"),
]

# Regex patterns that indicate token definitions
CSS_VAR_PATTERN = re.compile(r"--[\w-]+\s*:\s*([^;]+);")
SCSS_VAR_PATTERN = re.compile(r"\$[\w-]+\s*:\s*([^;]+);")
COLOR_HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COLOR_RGB_PATTERN = re.compile(r"rgba?\([^)]+\)")
COLOR_HSL_PATTERN = re.compile(r"hsla?\([^)]+\)")
SPACING_PATTERN = re.compile(r"(?:spacing|space|gap|padding|margin)[\w-]*\s*[:=]\s*", re.IGNORECASE)
FONT_PATTERN = re.compile(r"(?:font|typography|text)[\w-]*\s*[:=]\s*", re.IGNORECASE)
SHADOW_PATTERN = re.compile(r"(?:shadow|elevation)[\w-]*\s*[:=]\s*", re.IGNORECASE)
RADIUS_PATTERN = re.compile(r"(?:radius|rounded|border-radius)[\w-]*\s*[:=]\s*", re.IGNORECASE)


def analyze_css_file(file_path: Path) -> dict | None:
    """Check a CSS file for custom property definitions."""
    try:
        content = file_path.read_text(errors="ignore")
    except OSError:
        return None

    vars_found = CSS_VAR_PATTERN.findall(content)
    if not vars_found:
        return None

    # Categorize the variables
    categories = {
        "colors": 0,
        "spacing": 0,
        "typography": 0,
        "shadows": 0,
        "radius": 0,
        "other": 0,
    }

    color_samples = []
    spacing_samples = []

    for match in CSS_VAR_PATTERN.finditer(content):
        full_match = match.group(0)
        value = match.group(1).strip()

        if any(kw in full_match.lower() for kw in ["color", "bg", "text", "border-color", "fill", "stroke"]):
            categories["colors"] += 1
            if len(color_samples) < 5:
                color_samples.append(full_match.strip())
        elif any(kw in full_match.lower() for kw in ["space", "gap", "padding", "margin", "size"]):
            categories["spacing"] += 1
            if len(spacing_samples) < 5:
                spacing_samples.append(full_match.strip())
        elif any(kw in full_match.lower() for kw in ["font", "text", "letter", "line-height"]):
            categories["typography"] += 1
        elif any(kw in full_match.lower() for kw in ["shadow", "elevation"]):
            categories["shadows"] += 1
        elif any(kw in full_match.lower() for kw in ["radius", "rounded"]):
            categories["radius"] += 1
        elif COLOR_HEX_PATTERN.search(value) or COLOR_RGB_PATTERN.search(value) or COLOR_HSL_PATTERN.search(value):
            categories["colors"] += 1
            if len(color_samples) < 5:
                color_samples.append(full_match.strip())
        else:
            categories["other"] += 1

    total = sum(categories.values())
    if total < 3:
        return None

    return {
        "type": "css-custom-properties",
        "total_tokens": total,
        "categories": {k: v for k, v in categories.items() if v > 0},
        "color_samples": color_samples,
        "spacing_samples": spacing_samples,
    }


def analyze_tailwind_config(file_path: Path) -> dict | None:
    """Check a Tailwind config for theme extensions."""
    try:
        content = file_path.read_text(errors="ignore")
    except OSError:
        return None

    result = {
        "type": "tailwind-config",
        "has_custom_colors": False,
        "has_custom_spacing": False,
        "has_custom_fonts": False,
        "has_custom_shadows": False,
        "has_custom_radius": False,
        "extends_theme": "extend" in content,
        "uses_css_variables": "var(--" in content or "hsl(var(--" in content,
    }

    # Check for theme customizations
    if re.search(r"colors?\s*[:=]\s*\{", content):
        result["has_custom_colors"] = True
    if re.search(r"spacing\s*[:=]\s*\{", content):
        result["has_custom_spacing"] = True
    if re.search(r"font(?:Family|Size)\s*[:=]\s*\{", content):
        result["has_custom_fonts"] = True
    if re.search(r"(?:box)?[Ss]hadow\s*[:=]\s*\{", content):
        result["has_custom_shadows"] = True
    if re.search(r"(?:border)?[Rr]adius\s*[:=]\s*\{", content):
        result["has_custom_radius"] = True

    # Check if it has any customization at all
    has_any = any([
        result["has_custom_colors"],
        result["has_custom_spacing"],
        result["has_custom_fonts"],
        result["has_custom_shadows"],
        result["has_custom_radius"],
    ])

    if not has_any and not result["extends_theme"]:
        return None

    return result


def analyze_theme_file(file_path: Path) -> dict | None:
    """Check a JS/TS/JSON theme file for token definitions."""
    try:
        content = file_path.read_text(errors="ignore")[:10000]  # Cap file read
    except OSError:
        return None

    categories = {
        "colors": bool(re.search(r"colors?\s*[:=]\s*\{", content, re.IGNORECASE)),
        "spacing": bool(SPACING_PATTERN.search(content)),
        "typography": bool(FONT_PATTERN.search(content)),
        "shadows": bool(SHADOW_PATTERN.search(content)),
        "radius": bool(RADIUS_PATTERN.search(content)),
    }

    if not any(categories.values()):
        return None

    # Count approximate token count
    color_count = len(COLOR_HEX_PATTERN.findall(content)) + len(COLOR_RGB_PATTERN.findall(content))

    return {
        "type": "theme-file",
        "format": file_path.suffix,
        "categories": {k: v for k, v in categories.items() if v},
        "approximate_color_count": color_count,
    }


def analyze_scss_file(file_path: Path) -> dict | None:
    """Check SCSS/SASS files for variable definitions."""
    try:
        content = file_path.read_text(errors="ignore")
    except OSError:
        return None

    vars_found = SCSS_VAR_PATTERN.findall(content)
    if len(vars_found) < 3:
        return None

    return {
        "type": "scss-variables",
        "variable_count": len(vars_found),
        "has_colors": bool(COLOR_HEX_PATTERN.search(content)),
        "has_spacing": bool(SPACING_PATTERN.search(content)),
    }


def analyze_token_json(file_path: Path) -> dict | None:
    """Check JSON files for token structure (Style Dictionary, Tokens Studio, etc.)."""
    try:
        content = file_path.read_text(errors="ignore")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    # Look for token-like structure
    # Style Dictionary format: { "color": { "primary": { "value": "#..." } } }
    # Tokens Studio format: { "colors": { "primary": { "$value": "#..." } } }
    token_like_keys = {"color", "colors", "spacing", "space", "typography",
                       "font", "shadow", "radius", "size", "opacity"}

    found_categories = []
    for key in data:
        if key.lower() in token_like_keys:
            found_categories.append(key)

    # Also check for $value or value patterns (Style Dictionary / W3C format)
    content_str = content[:5000]
    has_value_pattern = '"value"' in content_str or '"$value"' in content_str

    if not found_categories and not has_value_pattern:
        return None

    return {
        "type": "token-json",
        "format": "style-dictionary" if has_value_pattern else "custom",
        "categories": found_categories,
    }


def find_token_sources(root: Path, context: dict) -> list[dict]:
    """Search the repository for design token definitions."""
    results = []
    seen_files = set()

    # Strategy 1: Check known file patterns
    for pattern, source_type in TOKEN_FILE_PATTERNS:
        try:
            for match in root.glob(pattern):
                if not match.is_file():
                    continue
                if any(skip in str(match) for skip in SKIP_DIRS):
                    continue

                resolved = match.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)

                rel_path = str(match.relative_to(root))
                analysis = None

                if match.suffix == ".css":
                    analysis = analyze_css_file(match)
                elif "tailwind.config" in match.name:
                    analysis = analyze_tailwind_config(match)
                elif match.suffix in {".json"} and "token" in match.name.lower():
                    analysis = analyze_token_json(match)
                elif match.suffix in {".scss", ".sass"}:
                    analysis = analyze_scss_file(match)
                elif match.suffix in {".js", ".ts", ".mjs", ".mts"}:
                    analysis = analyze_theme_file(match)

                if analysis:
                    results.append({
                        "path": rel_path,
                        "source_type": source_type,
                        **analysis,
                    })
        except (OSError, PermissionError):
            continue

    # Strategy 2: Search for CSS files with many custom properties
    # (catches globals.css, app.css, etc. that weren't in the patterns above)
    css_extensions = {".css", ".scss", ".sass", ".less"}
    search_dirs = [root / "src", root / "app", root / "styles", root / "css", root]

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        try:
            for css_file in search_dir.glob("**/*"):
                if not css_file.is_file() or css_file.suffix not in css_extensions:
                    continue
                if any(skip in str(css_file) for skip in SKIP_DIRS):
                    continue

                resolved = css_file.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)

                analysis = None
                if css_file.suffix == ".css":
                    analysis = analyze_css_file(css_file)
                elif css_file.suffix in {".scss", ".sass"}:
                    analysis = analyze_scss_file(css_file)

                if analysis:
                    rel_path = str(css_file.relative_to(root))
                    results.append({
                        "path": rel_path,
                        "source_type": "css-scan",
                        **analysis,
                    })
        except (OSError, PermissionError):
            continue

    # Sort by relevance (token count or category richness)
    def sort_key(item):
        total = item.get("total_tokens", 0)
        categories = item.get("categories", {})
        if isinstance(categories, dict):
            total += len(categories) * 10
        elif isinstance(categories, list):
            total += len(categories) * 10
        return total

    results.sort(key=sort_key, reverse=True)

    return results


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

    sources = find_token_sources(root, context)

    output = {
        "root": str(root),
        "token_sources": sources[:15],  # Top 15
        "total_found": len(sources),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
