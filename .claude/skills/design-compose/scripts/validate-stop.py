#!/usr/bin/env python3
"""
Stop-time validation: scans all UI files for token and import violations.

Reuses the same validation logic as validate-tokens.py and check-imports.py
but runs across all relevant files at once, as a final gate before stopping.

Hook handler: Stop
Exit 2 with feedback on violations (triggers re-prompt), exit 0 on pass.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def log_run(result: str):
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_dir / "validation.log", "a") as f:
        f.write(f"{ts} [validate-stop] ALL: {result}\n")


def load_module(name: str):
    """Load a sibling script as a module."""
    script_dir = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(name, script_dir / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_modified_ui_files(paths_config: dict) -> list[Path]:
    """Find UI files modified in the current git working tree."""
    import subprocess

    extensions = set(
        paths_config.get("ui_file_extensions", [".tsx", ".jsx", ".vue", ".svelte"])
    )

    # Component directory files define the system — skip them
    component_dirs = set(paths_config.get("component_directories_all", []))
    component_dir = paths_config.get("component_directory", "")
    if component_dir:
        component_dirs.add(component_dir)

    # Get modified + untracked files from git
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        modified = set(result.stdout.strip().splitlines())

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


def main():
    # Read stdin (Stop hook input) — we don't need it but must consume it
    try:
        sys.stdin.read()
    except Exception:
        pass

    # Load configs via the sibling modules
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

        # Token violations
        violations = tokens_mod.validate_content(content, str(file_path), token_config)
        for v in violations:
            all_issues.append(
                f"  {name}:{v['line']} — {v['description']}: `{v['match']}`. {v['fix_hint']}"
            )

        # Import violations (raw HTML instead of design system components)
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
