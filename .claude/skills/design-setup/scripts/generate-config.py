#!/usr/bin/env python3
"""
Generate design-compose configuration from confirmed setup answers.

Takes a JSON config on stdin and writes config files that design-compose
reads. Language-agnostic — forbidden patterns are generated dynamically
from the discovered token types, not hardcoded.

Usage:
  echo '<config_json>' | python3 generate-config.py
"""

import json
import sys
from pathlib import Path


def generate_component_map(config: dict) -> dict:
    """Generate component-map.json from confirmed components."""
    components = config.get("confirmed_components", [])
    component_map = {}

    for comp in components:
        name = comp.get("name", "")
        import_path = comp.get("import_path", "")
        replaces = comp.get("replaces", "")

        if replaces and name:
            hint = f"Use {name}"
            if import_path:
                hint += f" from '{import_path}'"
            variants = comp.get("variants", [])
            if variants:
                hint += f". Variants: {', '.join(variants)}"
            component_map[replaces] = hint

    return component_map


def generate_token_patterns(config: dict) -> dict:
    """
    Generate token-patterns.json dynamically from discovered token types.

    Instead of hardcoding CSS-specific patterns, we build forbidden patterns
    based on what token categories were found. If the project has color tokens,
    we forbid raw color literals. If it has spacing tokens, we forbid raw
    size literals in spacing contexts.
    """
    token_sources = config.get("confirmed_token_sources", [])
    discovered_categories = set()
    for source in token_sources:
        for cat in source.get("categories", []):
            discovered_categories.add(cat)

    patterns = {
        "ecosystem": config.get("ecosystem", ""),
        "language": config.get("language", ""),
        "token_sources": [s.get("path", "") for s in token_sources],
        "forbidden_patterns": [],
        "allowed_exceptions": ["0px", "1px", "0dp", "1dp", "100%"],
    }

    # Generate forbidden patterns based on discovered token categories
    token_hint = "Use a design token"
    source_names = [s.get("path", "").split("/")[-1] for s in token_sources]
    if source_names:
        token_hint += f" (defined in {', '.join(source_names)})"

    if "color" in discovered_categories:
        patterns["forbidden_patterns"].extend([
            {
                "pattern": r"#[0-9a-fA-F]{3,8}\b",
                "description": "hardcoded hex color",
                "fix_hint": token_hint,
            },
            {
                "pattern": r"rgba?\s*\(\s*\d+",
                "description": "hardcoded RGB color",
                "fix_hint": token_hint,
            },
            {
                "pattern": r"hsla?\s*\(\s*\d+",
                "description": "hardcoded HSL color",
                "fix_hint": token_hint,
            },
            {
                "pattern": r"oklch\s*\(",
                "description": "hardcoded oklch color",
                "fix_hint": token_hint,
            },
        ])

    if "size" in discovered_categories:
        spacing_base = config.get("spacing_base_px")
        spacing_hint = token_hint
        if spacing_base:
            spacing_hint += f" (base unit: {spacing_base}px)"

        patterns["forbidden_patterns"].append({
            "pattern": r"\d+px\b",
            "description": "hardcoded pixel value",
            "fix_hint": spacing_hint,
            "context_hint": "Check if this is in a spacing/sizing context",
        })

    if "font" in discovered_categories:
        patterns["forbidden_patterns"].append({
            "pattern": r"font-size:\s*\d+",
            "description": "hardcoded font size",
            "fix_hint": token_hint,
        })

    # Spacing base
    spacing_base = config.get("spacing_base_px")
    if spacing_base:
        patterns["spacing_base_px"] = spacing_base

    return patterns


def generate_paths_config(config: dict) -> dict:
    """Generate paths.json for design-compose scripts."""
    return {
        "ecosystem": config.get("ecosystem", ""),
        "language": config.get("language", ""),
        "component_directory": config.get("component_directory", ""),
        "component_directories_all": config.get("component_directories_all", []),
        "token_sources": [s.get("path", "") for s in config.get("confirmed_token_sources", [])],
        "composition_examples": config.get("composition_examples", []),
        "skip_directories": config.get("skip_directories", list(
            {"node_modules", ".git", "dist", "build", ".next", ".nuxt",
             ".svelte-kit", ".dart_tool", "Pods", "target"}
        )),
        "ui_file_extensions": config.get("ui_file_extensions", []),
    }


def generate_composition_rules(config: dict) -> dict:
    """Generate composition-rules.json for compound component checking."""
    components = config.get("confirmed_components", [])
    rules = {
        "controlled_components": [],
        "compound_patterns": {},
    }

    for comp in components:
        name = comp.get("name", "")
        children = comp.get("expected_children", [])
        is_controlled = comp.get("style_controlled", False)

        if is_controlled:
            rules["controlled_components"].append(name)
        if children:
            rules["compound_patterns"][name] = {
                "expected_children": children,
                "message": f"{name} should be composed with: {', '.join(children)}",
            }

    return rules


def write_config(output_dir: Path, config: dict):
    """Write all config files to the design-compose config directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    configs = {
        "component-map.json": generate_component_map(config),
        "token-patterns.json": generate_token_patterns(config),
        "paths.json": generate_paths_config(config),
        "composition-rules.json": generate_composition_rules(config),
    }

    written = []
    for filename, data in configs.items():
        file_path = output_dir / filename
        file_path.write_text(json.dumps(data, indent=2) + "\n")
        written.append(str(file_path))

    return written


def main():
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    output_dir_str = config.get("output_directory", "")
    if not output_dir_str:
        script_dir = Path(__file__).parent.parent
        output_dir = script_dir.parent / "design-compose" / "config"
    else:
        output_dir = Path(output_dir_str)

    written = write_config(output_dir, config)

    result = {
        "success": True,
        "files_written": written,
        "output_directory": str(output_dir),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
