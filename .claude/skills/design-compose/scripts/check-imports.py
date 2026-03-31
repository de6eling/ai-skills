#!/usr/bin/env python3
"""
check-imports.py — Makes sure the AI uses your components
=========================================================

WHAT THIS DOES:
  Your design system has components like Button, Input, Card — built to
  look and behave a specific way. Sometimes AI writes plain HTML like
  <button> or <input> instead of using your components. This script
  catches that.

  It's like having a reviewer who says "hey, we have a Button component
  for that — use it instead of a raw <button> tag."

WHEN DOES IT RUN:
  Every time AI writes or edits a file. Completely automatic.

WHAT HAPPENS WHEN IT FINDS SOMETHING:
  - Clean file: nothing visible, AI keeps going
  - Problem found: AI is told which line has a raw HTML element and
    which design system component to use instead

WHERE TO SEE THE RESULTS:
  Open .claude/logs/validation.log — you'll see entries like:
    2026-03-31T04:27:20 [check-imports] page.tsx: PASS
    2026-03-31T04:27:20 [check-imports] page.tsx: FAIL (1 violations)

HOW IT KNOWS WHICH COMPONENTS EXIST:
  It reads config/component-map.json — the catalog of all your design
  system components. Each entry has a component name and a description
  of how to use it. For example:
    "button" → "Use Button from '@/components/ui/button'. Variants: ..."

  If a catalog entry starts with "<" (like "<button>"), the script will
  look for that raw HTML tag in your code. With the default catalog
  format (plain names like "button"), this script serves as a
  placeholder — ready to enforce raw-HTML-to-component rules if you
  add entries like "<button>" to your catalog.

  The catalog is created by /design-setup and grows as you add new
  components during compose sessions.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Write a line to the log file so there's a record of every run.
# ---------------------------------------------------------------------------

def log_run(script: str, file_path: str, result: str):
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    name = Path(file_path).name if file_path else "N/A"
    with open(log_dir / "validation.log", "a") as f:
        f.write(f"{ts} [{script}] {name}: {result}\n")


# ---------------------------------------------------------------------------
# Load the component catalog and project settings.
# ---------------------------------------------------------------------------

def load_config() -> tuple[dict, dict]:
    script_dir = Path(__file__).parent.parent

    map_path = script_dir / "config" / "component-map.json"
    component_map = {}
    if map_path.exists():
        try:
            component_map = json.loads(map_path.read_text())
        except json.JSONDecodeError:
            pass

    paths_path = script_dir / "config" / "paths.json"
    paths_config = {}
    if paths_path.exists():
        try:
            paths_config = json.loads(paths_path.read_text())
        except json.JSONDecodeError:
            pass

    return component_map, paths_config


# ---------------------------------------------------------------------------
# Should we check this file? Skip anything that isn't UI code, or that
# defines the design system itself.
# ---------------------------------------------------------------------------

def is_relevant(file_path: str, paths_config: dict) -> bool:
    if not file_path:
        return False

    path = Path(file_path)
    extensions = paths_config.get("ui_file_extensions", [".tsx", ".jsx", ".vue", ".svelte"])

    if path.suffix not in extensions:
        return False

    if any(p in path.name for p in [".test.", ".spec.", ".stories.", ".story."]):
        return False

    component_dirs = paths_config.get("component_directories_all", [])
    component_dir = paths_config.get("component_directory", "")
    all_dirs = set(component_dirs)
    if component_dir:
        all_dirs.add(component_dir)

    for d in all_dirs:
        if d and d in str(path):
            return False

    skip_dirs = paths_config.get("skip_directories", [])
    if set(path.parts) & set(skip_dirs):
        return False

    return True


# ---------------------------------------------------------------------------
# Entry point: read the file, check each line for raw HTML elements
# that should be using a design system component instead.
#
# We only flag things that look like HTML tags (starting with "<") to
# avoid false alarms on words like "button" appearing in variable names.
#
# Exit code 0 = everything is fine
# Exit code 2 = problems found, the AI needs to fix them
# ---------------------------------------------------------------------------

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    component_map, paths_config = load_config()

    if not component_map:
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

    violations = []

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()

        if stripped.startswith("//") or stripped.startswith("{/*") or stripped.startswith("*"):
            continue
        # Import lines are fine — importing a component IS using the system
        if stripped.startswith("import "):
            continue

        for raw_element, replacement in component_map.items():
            if raw_element.startswith("<"):
                if raw_element.lower() in line.lower():
                    violations.append(
                        f"Line {line_num}: found `{raw_element.strip()}` — {replacement}"
                    )

    if not violations:
        log_run("check-imports", file_path, "PASS")
        print(f"✓ check-imports: PASS — design system components used correctly in {Path(file_path).name}")
        sys.exit(0)

    log_run("check-imports", file_path, f"FAIL ({len(violations)} violations)")

    feedback = (
        f"Component violations in {file_path}:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nUse design system components instead of raw HTML elements."
    )

    print(feedback, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
