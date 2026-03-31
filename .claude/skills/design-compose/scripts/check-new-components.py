#!/usr/bin/env python3
"""
Detect design system components used in a file that aren't yet in the catalog.

Parses import statements deterministically — no LLM judgment. Compares the
last path segment of each @/components/ui/* import against component-map.json
keys. If new components are found, exits 2 with a message so Claude asks
the user whether to add them to the catalog.

Hook handler: PostToolUse on Edit|Write
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def log_run(script: str, file_path: str, result: str):
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    name = Path(file_path).name if file_path else "N/A"
    with open(log_dir / "validation.log", "a") as f:
        f.write(f"{ts} [{script}] {name}: {result}\n")


def load_config() -> tuple[set[str], dict]:
    script_dir = Path(__file__).parent.parent

    # Collect all known component names (lowercase) from both catalog files
    known: set[str] = set()

    map_path = script_dir / "config" / "component-map.json"
    if map_path.exists():
        try:
            data = json.loads(map_path.read_text())
            known.update(k.lower() for k in data)
        except json.JSONDecodeError:
            pass

    rules_path = script_dir / "config" / "composition-rules.json"
    if rules_path.exists():
        try:
            data = json.loads(rules_path.read_text())
            # controlled_components list
            for name in data.get("controlled_components", []):
                known.add(name.lower())
            # compound_patterns keys
            for name in data.get("compound_patterns", {}):
                known.add(name.lower())
        except json.JSONDecodeError:
            pass

    paths_path = script_dir / "config" / "paths.json"
    paths_config = {}
    if paths_path.exists():
        try:
            paths_config = json.loads(paths_path.read_text())
        except json.JSONDecodeError:
            pass

    return known, paths_config


def is_relevant(file_path: str, paths_config: dict) -> bool:
    path = Path(file_path)
    extensions = paths_config.get("ui_file_extensions", [".tsx", ".jsx", ".vue", ".svelte"])

    if path.suffix not in extensions:
        return False

    if any(p in path.name for p in [".test.", ".spec.", ".stories.", ".story.", ".d.ts"]):
        return False

    # Skip the component directory itself (these files define components, not consume them)
    all_dirs = set(paths_config.get("component_directories_all", []))
    component_dir = paths_config.get("component_directory", "")
    if component_dir:
        all_dirs.add(component_dir)
    for d in all_dirs:
        if d and d in str(path).replace("\\", "/"):
            return False

    skip_dirs = paths_config.get("skip_directories", [])
    if set(path.parts) & set(skip_dirs):
        return False

    return True


def get_component_dir_fragment(paths_config: dict) -> str:
    """
    Return the fragment of the component directory used to match import paths.

    e.g. 'src/components/ui'  -> 'components/ui'
         '$lib/components/ui' -> 'components/ui'
    """
    raw = paths_config.get("component_directory", "src/components/ui")
    # Strip common source root prefixes so we match any alias (@/, $lib/, ~/, etc.)
    for prefix in ("src/", "$lib/", "lib/", "app/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    return raw


def find_design_system_imports(content: str, component_dir_fragment: str) -> list[tuple[str, str]]:
    """
    Return (catalog_key, import_path) pairs for each unique design system import.
    catalog_key is the last segment of the import path, lowercased (e.g. 'button').
    """
    # Match: import { ... } from '...' or import Something from '...'
    pattern = re.compile(
        r"""^import\s+(?:\{[^}]+\}|\w+)\s+from\s+['"]([^'"]+)['"]""",
        re.MULTILINE,
    )

    seen: set[str] = set()
    results: list[tuple[str, str]] = []

    for match in pattern.finditer(content):
        import_path = match.group(1)
        normalized = import_path.replace("\\", "/")

        if component_dir_fragment not in normalized:
            continue

        # Last segment = component file name (strip .tsx/.js etc. if present)
        last = normalized.split("/")[-1]
        catalog_key = re.sub(r"\.[a-z]+$", "", last).lower()

        if catalog_key and catalog_key not in seen:
            seen.add(catalog_key)
            results.append((catalog_key, import_path))

    return results


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    known, paths_config = load_config()

    if not known:
        sys.exit(0)

    if not is_relevant(file_path, paths_config):
        sys.exit(0)

    path = Path(file_path)
    if not path.exists():
        sys.exit(0)

    try:
        content = path.read_text(errors="ignore")
    except OSError:
        sys.exit(0)

    component_dir_fragment = get_component_dir_fragment(paths_config)
    ds_imports = find_design_system_imports(content, component_dir_fragment)

    if not ds_imports:
        sys.exit(0)

    new_components = [
        (key, import_path)
        for key, import_path in ds_imports
        if key not in known
    ]

    if not new_components:
        log_run("check-new-components", file_path, "PASS (all in catalog)")
        print(f"✓ check-new-components: PASS — all components in {Path(file_path).name} are in the catalog")
        sys.exit(0)

    names = ", ".join(k for k, _ in new_components)
    log_run("check-new-components", file_path, f"FLAGGED ({names})")

    lines = [
        f"New design system component(s) in {Path(file_path).name} not yet in the catalog:",
    ]
    for key, import_path in new_components:
        lines.append(f"  - {key}  (from '{import_path}')")
    lines.append("")
    lines.append("For each component above, ask the user:")
    lines.append("  'Add [ComponentName] to the design system catalog?'")
    lines.append("    yes — reusable across the project → add to component-map.json")
    lines.append("    no  — one-off for this page → skip")
    lines.append("")
    lines.append("If any compound sub-components were used (e.g. CardHeader, TableRow),")
    lines.append("also add a compound_patterns entry to composition-rules.json for 'yes' items.")

    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
