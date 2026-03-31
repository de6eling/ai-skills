#!/usr/bin/env python3
"""
validate-stop.py — Final check before the session ends
=======================================================

WHAT THIS DOES:
  When a design-compose session finishes, this script does one last
  sweep of all the files that were changed. It runs the same checks
  as validate-tokens.py and check-imports.py, but across every file
  you touched — not just the last one written.

  Think of it as a final quality gate before the work is done.

WHEN DOES IT RUN:
  Once, right when the session is about to end. If it finds problems,
  the AI is sent back to fix them before it can finish.

WHAT HAPPENS WHEN IT FINDS SOMETHING:
  - All files clean: session ends normally
  - Problems found: AI gets a list of every issue across every file
    and has to fix all of them before the session can end

WHICH FILES DOES IT CHECK:
  Only files that were changed in the current session. It uses git to
  figure out which files are new or modified. This means you won't be
  blocked by pre-existing issues in files you didn't touch.

  We started by checking ALL files in the project, but that was too
  aggressive — designers were getting blocked by problems in code they
  didn't write. Scoping to "your changes only" fixed that.

WHERE TO SEE THE RESULTS:
  Open .claude/logs/validation.log — you'll see:
    [validate-stop] ALL: PASS (10 files checked)
    [validate-stop] ALL: FAIL (3 issues in 10 files)

HOW IT REUSES THE OTHER SCRIPTS:
  Instead of duplicating the checking logic, this script loads
  validate-tokens.py and check-imports.py as helpers and calls their
  functions directly. If those scripts are updated, this one
  automatically benefits.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Write a line to the log file.
# ---------------------------------------------------------------------------

def log_run(result: str):
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_dir / "validation.log", "a") as f:
        f.write(f"{ts} [validate-stop] ALL: {result}\n")


# ---------------------------------------------------------------------------
# Load a sibling script so we can call its functions. This is how
# validate-stop reuses the checking logic from the other scripts.
# ---------------------------------------------------------------------------

def load_module(name: str):
    script_dir = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(name, script_dir / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Find all UI files that were changed or created since the last commit.
# Uses git to figure out what's new or modified. Skips the same things
# as the per-file scripts: component sources, token files, tests, etc.
# ---------------------------------------------------------------------------

def find_modified_ui_files(paths_config: dict) -> list[Path]:
    import subprocess

    extensions = set(
        paths_config.get("ui_file_extensions", [".tsx", ".jsx", ".vue", ".svelte"])
    )

    component_dirs = set(paths_config.get("component_directories_all", []))
    component_dir = paths_config.get("component_directory", "")
    if component_dir:
        component_dirs.add(component_dir)

    # Ask git: what changed since the last commit?
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        modified = set(result.stdout.strip().splitlines())

        # Also grab brand-new files that haven't been committed yet
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=10,
        )
        modified.update(result.stdout.strip().splitlines())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    cwd = Path.cwd()
    results = []

    for rel_str in modified:
        if not rel_str:
            continue

        path = cwd / rel_str
        if not path.exists():
            continue

        if path.suffix not in extensions:
            continue

        if any(p in path.name for p in [".test.", ".spec.", ".stories.", ".story.", ".d.ts"]):
            continue

        norm = rel_str.replace("\\", "/")
        if any(d and d in norm for d in component_dirs):
            continue

        token_sources = paths_config.get("token_sources", [])
        if any(ts and norm.endswith(ts) for ts in token_sources):
            continue

        results.append(path)

    return sorted(results)


# ---------------------------------------------------------------------------
# Entry point: find all changed files, run both checks on each one.
#
# Exit code 0 = everything is clean
# Exit code 2 = problems found, AI has to fix them before finishing
# ---------------------------------------------------------------------------

def main():
    # Read and discard the input (we don't need it, but we have to
    # consume it or the script hangs)
    try:
        sys.stdin.read()
    except Exception:
        pass

    # Load the checking logic from the other scripts
    tokens_mod = load_module("validate-tokens")
    imports_mod = load_module("check-imports")

    token_config = tokens_mod.load_config()
    paths_config = tokens_mod.load_paths_config()
    component_map, _ = imports_mod.load_config()

    ui_files = find_modified_ui_files(paths_config)

    if not ui_files:
        log_run("PASS (no UI files)")
        sys.exit(0)

    all_issues = []

    for file_path in ui_files:
        try:
            content = file_path.read_text(errors="ignore")
        except OSError:
            continue

        name = file_path.relative_to(Path.cwd())

        # Check 1: hardcoded colors, sizes, etc.
        violations = tokens_mod.validate_content(content, str(file_path), token_config)
        for v in violations:
            all_issues.append(
                f"  {name}:{v['line']} — {v['description']}: `{v['match']}`. {v['fix_hint']}"
            )

        # Check 2: raw HTML instead of design system components
        if component_map:
            for line_num, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("{/*") or stripped.startswith("*"):
                    continue
                if stripped.startswith("import "):
                    continue
                for raw_element, replacement in component_map.items():
                    if raw_element.startswith("<") and raw_element.lower() in line.lower():
                        all_issues.append(
                            f"  {name}:{line_num} — found `{raw_element}` → {replacement}"
                        )

    if not all_issues:
        log_run(f"PASS ({len(ui_files)} files checked)")
        print(f"✓ validate-stop: PASS — {len(ui_files)} modified files checked, no design system violations")
        sys.exit(0)

    log_run(f"FAIL ({len(all_issues)} issues in {len(ui_files)} files)")

    feedback = (
        f"Design system violations found across {len(ui_files)} UI files:\n"
        + "\n".join(all_issues)
        + "\n\nFix these violations before finishing."
    )

    print(feedback, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
