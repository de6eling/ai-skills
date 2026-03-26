#!/usr/bin/env python3
"""
Generate the design-compose configuration files from setup answers.

Takes a JSON config on stdin containing the confirmed setup answers
and writes the config files that design-compose's scripts read.

This is typically called by Claude after the interactive Q&A is complete,
passing in the collected answers as JSON.
"""

import json
import re
import sys
from pathlib import Path


def generate_component_map(config: dict) -> dict:
    """Generate the component-map.json from confirmed components."""
    component_dir = config.get("component_directory", "")
    components = config.get("confirmed_components", [])
    framework = config.get("framework", "react")

    component_map = {}

    # Build map from confirmed components
    for comp in components:
        name = comp.get("name", "")
        file_path = comp.get("file", "")
        import_path = comp.get("import_path", "")
        raw_element = comp.get("replaces_element", "")

        if raw_element and name:
            hint = f"Use <{name}>"
            if import_path:
                hint += f" from '{import_path}'"
            variants = comp.get("variants", [])
            if variants:
                hint += f". Variants: {', '.join(variants)}"
            component_map[raw_element] = hint

    return component_map


def generate_token_patterns(config: dict) -> dict:
    """Generate token-patterns.json for the validator scripts."""
    token_system = config.get("token_system", "tailwind")
    token_sources = config.get("confirmed_token_sources", [])

    patterns = {
        "token_system": token_system,
        "token_sources": [s.get("path", "") for s in token_sources],
        "forbidden_patterns": [],
        "allowed_exceptions": [],
    }

    # Base forbidden patterns (always forbidden)
    patterns["forbidden_patterns"] = [
        {
            "pattern": r"[\"']#[0-9a-fA-F]{3,8}[\"']",
            "description": "hardcoded hex color in attribute",
            "fix_hint": "Use a design token or CSS variable",
        },
        {
            "pattern": r":\s*#[0-9a-fA-F]{3,8}",
            "description": "hardcoded hex color in style",
            "fix_hint": "Use a design token or CSS variable",
        },
        {
            "pattern": r"rgba?\(\s*\d+",
            "description": "hardcoded RGB color",
            "fix_hint": "Use a design token or CSS variable",
        },
        {
            "pattern": r"font-size:\s*\d+px",
            "description": "hardcoded font size",
            "fix_hint": "Use a typography token",
        },
    ]

    # Spacing patterns depend on the system
    spacing_base = config.get("spacing_base", 4)
    if spacing_base:
        patterns["spacing_base"] = spacing_base
        patterns["forbidden_patterns"].append({
            "pattern": r"(?:margin|padding|gap).*?:\s*\d+px",
            "description": "hardcoded spacing value",
            "fix_hint": f"Use a spacing token (base unit: {spacing_base}px)",
        })

    # Allowed exceptions (things that look like violations but aren't)
    patterns["allowed_exceptions"] = [
        r"0px",  # Zero is always fine
        r"1px",  # Borders are typically 1px
        r"100%",  # Percentage values
        r"\.5px",  # Sub-pixel for borders
    ]

    return patterns


def generate_paths_config(config: dict) -> dict:
    """Generate paths.json so scripts know where to look."""
    return {
        "component_directory": config.get("component_directory", ""),
        "component_directories_all": config.get("component_directories_all", []),
        "token_sources": [s.get("path", "") for s in config.get("confirmed_token_sources", [])],
        "page_directories": config.get("page_directories", []),
        "skip_directories": config.get("skip_directories", [
            "node_modules", ".git", "dist", "build", ".next", ".nuxt"
        ]),
        "ui_file_extensions": config.get("component_extensions", [".tsx", ".jsx"]),
        "framework": config.get("framework", ""),
        "framework_name": config.get("framework_name", ""),
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
    # Read config from stdin
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    # Determine output directory
    output_dir_str = config.get("output_directory", "")
    if not output_dir_str:
        # Default: sibling design-compose skill's config directory
        script_dir = Path(__file__).parent.parent  # design-setup/
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
