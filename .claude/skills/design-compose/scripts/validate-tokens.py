#!/usr/bin/env python3
"""
validate-tokens.py — Catches hardcoded colors and sizes
========================================================

WHAT THIS DOES:
  Every design system has shared color and size values (called "tokens")
  so everything looks consistent. When AI writes code, it sometimes
  uses raw values like "#383838" instead of your design system's named
  colors. This script catches that automatically.

  Think of it like spell-check, but for design consistency.

WHEN DOES IT RUN:
  Every time AI writes or edits a file. You don't have to do anything —
  it runs in the background. If it finds a problem, the AI gets told
  to fix it before moving on.

WHAT HAPPENS WHEN IT FINDS SOMETHING:
  - If the file is clean: the result is recorded in the log file
    (see below) and the AI reports it in its response. Nothing
    else visible in the chat — clean passes are quiet by design.
  - If there's a problem: the AI is told exactly which line has the
    issue and how to fix it (e.g. "Line 42: hardcoded hex color —
    use a design token instead"). This DOES show in the chat.

WHERE TO SEE THE RESULTS:
  Open .claude/logs/validation.log — every time this script runs, it
  writes a line like:
    2026-03-31T04:27:20 [validate-tokens] page.tsx: PASS
    2026-03-31T04:27:20 [validate-tokens] page.tsx: FAIL (2 violations)

HOW IT DECIDES WHAT'S WRONG:
  It reads a list of "forbidden patterns" from a config file
  (config/token-patterns.json). Each pattern is a search rule like
  "any hex color code" or "any rgb() value". The config file is
  created by /design-setup when you first set up the skill.

  Some values are allowed even though they match — like "0px" or "1px"
  or "100%". These are listed as exceptions in the config.

WHAT FILES DOES IT SKIP:
  - Files that aren't UI code (like .json, .md, etc.)
  - Test files and Storybook stories
  - The component source files themselves (they define the system)
  - The token definition files (like globals.css)
  - Anything in node_modules, .git, etc.
"""

import json
import re
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
# Load the list of forbidden patterns (hex colors, rgb values, etc.)
# from the config file. If the config doesn't exist, use some defaults.
# ---------------------------------------------------------------------------

def load_config() -> dict:
    script_dir = Path(__file__).parent.parent
    config_path = script_dir / "config" / "token-patterns.json"

    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except json.JSONDecodeError:
            pass

    return {
        "token_system": "unknown",
        "forbidden_patterns": [
            {
                "pattern": r"[\"']#[0-9a-fA-F]{3,8}[\"']",
                "description": "hardcoded hex color",
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
        ],
        "allowed_exceptions": [r"0px", r"1px", r"100%"],
    }


# ---------------------------------------------------------------------------
# Load project settings — tells us which file types to check and which
# folders to skip.
# ---------------------------------------------------------------------------

def load_paths_config() -> dict:
    script_dir = Path(__file__).parent.parent
    config_path = script_dir / "config" / "paths.json"

    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except json.JSONDecodeError:
            pass

    return {
        "ui_file_extensions": [".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss"],
        "skip_directories": ["node_modules", ".git", "dist", "build"],
        "component_directory": "",
    }


# ---------------------------------------------------------------------------
# Should we check this file? Skip anything that isn't a UI file, or that
# defines the design system itself (we only check files that USE it).
# ---------------------------------------------------------------------------

def is_relevant(file_path: str, paths_config: dict) -> bool:
    if not file_path:
        return False

    path = Path(file_path)
    extensions = paths_config.get("ui_file_extensions", [".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss"])

    if path.suffix not in extensions:
        return False

    skip_patterns = [".test.", ".spec.", ".stories.", ".story.", ".d.ts"]
    if any(p in path.name for p in skip_patterns):
        return False

    skip_dirs = paths_config.get("skip_directories", [])
    if set(path.parts) & set(skip_dirs):
        return False

    # Skip files that define the tokens (like globals.css)
    token_sources = paths_config.get("token_sources", [])
    for ts in token_sources:
        if ts and str(path).endswith(ts):
            return False

    # Skip component source files (like button.tsx in the ui folder)
    component_dir = paths_config.get("component_directory", "")
    if component_dir and str(path).replace("\\", "/").find(component_dir) >= 0:
        return False

    return True


# ---------------------------------------------------------------------------
# The actual checking: go through the file line by line and look for
# forbidden patterns. If a line matches a forbidden pattern but is also
# an allowed exception (like "0px"), skip it.
# ---------------------------------------------------------------------------

def validate_content(content: str, file_path: str, config: dict) -> list[dict]:
    violations = []
    forbidden = config.get("forbidden_patterns", [])
    exceptions = config.get("allowed_exceptions", [])

    compiled_exceptions = [re.compile(ex) for ex in exceptions]

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()

        # Skip comments — they're notes, not code
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        if stripped.startswith("{/*"):
            continue

        for rule in forbidden:
            pattern = rule.get("pattern", "")
            if not pattern:
                continue

            try:
                match = re.search(pattern, line)
            except re.error:
                continue

            if not match:
                continue

            matched_text = match.group()

            # Is this an allowed exception?
            is_exception = False
            for exc in compiled_exceptions:
                if exc.search(matched_text):
                    is_exception = True
                    break

            if is_exception:
                continue

            violations.append({
                "line": line_num,
                "match": matched_text,
                "description": rule.get("description", "forbidden pattern"),
                "fix_hint": rule.get("fix_hint", "Use a design token"),
            })

    return violations


# ---------------------------------------------------------------------------
# Entry point: read what file was written, check it, report results.
#
# The AI tool sends us information about what just happened through
# "standard input" (stdin) as a JSON message. We read that to find
# out which file to check.
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

    config = load_config()
    paths_config = load_paths_config()

    if not is_relevant(file_path, paths_config):
        sys.exit(0)

    path = Path(file_path)
    if not path.exists():
        sys.exit(0)

    try:
        content = path.read_text(errors="ignore")
    except OSError:
        sys.exit(0)

    violations = validate_content(content, file_path, config)

    if not violations:
        log_run("validate-tokens", file_path, "PASS")
        print(f"✓ validate-tokens: PASS — no hardcoded values in {Path(file_path).name}")
        sys.exit(0)

    log_run("validate-tokens", file_path, f"FAIL ({len(violations)} violations)")

    # Tell the AI what's wrong so it can fix it
    lines = [f"Design token violations in {file_path}:"]
    for v in violations:
        lines.append(f"  - Line {v['line']}: {v['description']} — found `{v['match']}`. {v['fix_hint']}.")

    token_sources = config.get("token_sources", [])
    if token_sources:
        lines.append(f"\nToken definitions: {', '.join(token_sources)}")

    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
