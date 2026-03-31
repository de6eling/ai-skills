#!/usr/bin/env python3
"""
check-new-components.py — Discovers components not yet in the catalog
=====================================================================

WHAT THIS DOES:
  When AI builds a page, it might install or use components that aren't
  yet documented in the design system catalog. This script notices that
  and asks you: "Should this be added to the catalog?"

  For example, if the AI installs a Badge component and uses it, but
  Badge isn't in your catalog yet, this script flags it. You decide:
  keep it as a one-off, or add it so future sessions know about it.

WHEN DOES IT RUN:
  Every time AI writes or edits a file. Completely automatic.

WHAT HAPPENS WHEN IT FINDS SOMETHING:
  The AI pauses and asks you about each new component:
    "New component: badge (from @/components/ui/badge)
     Add to the design system catalog?
     yes — reusable, use everywhere
     no — one-off, just for this page"

  If you say yes, the AI adds it to component-map.json (and
  composition-rules.json if it has sub-parts like CardHeader).

WHY THIS USES CODE INSTEAD OF AI JUDGMENT:
  We originally had the AI decide whether components were "new." It was
  unreliable — it would say things were already cataloged when they
  weren't, or flag things that were already there. This script reads
  the actual files and compares them directly. No guessing.

WHERE TO SEE THE RESULTS:
  Open .claude/logs/validation.log — you'll see entries like:
    [check-new-components] page.tsx: PASS (all in catalog)
    [check-new-components] page.tsx: FLAGGED (badge, slider)

HOW IT DECIDES WHAT'S "KNOWN":
  A component is considered "known" if it appears in ANY of these:
  - component-map.json (the main catalog)
  - composition-rules.json's "controlled_components" list
  - composition-rules.json's "compound_patterns" section

  If it's not in any of those, it's flagged as new.

HOW IT READS IMPORTS:
  It looks at the import lines at the top of the file, like:
    import { Badge } from '@/components/ui/badge'

  It takes the last part of the path ("badge"), lowercases it, and
  checks if that name is in the catalog. This works across different
  frameworks (Next.js uses @/, SvelteKit uses $lib/, etc.) because
  it strips those prefixes when matching.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Write a line to the log file.
# ---------------------------------------------------------------------------

def log_run(script: str, file_path: str, result: str):
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    name = Path(file_path).name if file_path else "N/A"
    with open(log_dir / "validation.log", "a") as f:
        f.write(f"{ts} [{script}] {name}: {result}\n")


# ---------------------------------------------------------------------------
# Build the list of component names the system already knows about.
# We check two config files because components can be documented in
# either one (or both).
# ---------------------------------------------------------------------------

def load_config() -> tuple[set[str], dict]:
    script_dir = Path(__file__).parent.parent

    known: set[str] = set()

    # The main component catalog
    map_path = script_dir / "config" / "component-map.json"
    if map_path.exists():
        try:
            data = json.loads(map_path.read_text())
            known.update(k.lower() for k in data)
        except json.JSONDecodeError:
            pass

    # The composition rules (also lists known components)
    rules_path = script_dir / "config" / "composition-rules.json"
    if rules_path.exists():
        try:
            data = json.loads(rules_path.read_text())
            for name in data.get("controlled_components", []):
                known.add(name.lower())
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


# ---------------------------------------------------------------------------
# Should we check this file?
# ---------------------------------------------------------------------------

def is_relevant(file_path: str, paths_config: dict) -> bool:
    path = Path(file_path)
    extensions = paths_config.get("ui_file_extensions", [".tsx", ".jsx", ".vue", ".svelte"])

    if path.suffix not in extensions:
        return False

    if any(p in path.name for p in [".test.", ".spec.", ".stories.", ".story.", ".d.ts"]):
        return False

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


# ---------------------------------------------------------------------------
# Figure out what to look for in import paths.
#
# The component folder might be "src/components/ui" but imports use
# "@/components/ui/badge" (the "src/" is replaced by "@/"). So we
# strip the "src/" part and just look for "components/ui" in the path.
# ---------------------------------------------------------------------------

def get_component_dir_fragment(paths_config: dict) -> str:
    raw = paths_config.get("component_directory", "src/components/ui")
    for prefix in ("src/", "$lib/", "lib/", "app/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    return raw


# ---------------------------------------------------------------------------
# Find all design system imports in the file.
#
# Looks at lines like:
#   import { Badge } from '@/components/ui/badge'
#
# Returns the component name ("badge") and the full import path.
# ---------------------------------------------------------------------------

def find_design_system_imports(content: str, component_dir_fragment: str) -> list[tuple[str, str]]:
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

        # Get the component name from the end of the path
        last = normalized.split("/")[-1]
        catalog_key = re.sub(r"\.[a-z]+$", "", last).lower()

        if catalog_key and catalog_key not in seen:
            seen.add(catalog_key)
            results.append((catalog_key, import_path))

    return results


# ---------------------------------------------------------------------------
# Entry point: compare the file's imports against the catalog.
#
# Exit code 0 = all components are already known
# Exit code 2 = new components found, AI will ask you about them
# ---------------------------------------------------------------------------

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

    # Which imports are NOT in the catalog?
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

    # Tell the AI to ask the designer about each new component
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
