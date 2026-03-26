# Part 6: Writing Good Validator Scripts

Most hook documentation shows you the configuration — how to wire up a hook in settings.json, which events to use, how matchers work. This part covers what's inside the scripts themselves. The validator script is where enforcement actually happens, and the difference between a good one and a bad one determines whether the feedback loop works or wastes tokens.

## The Anatomy of a Validator Script

Every command handler script follows the same structure:

```python
#!/usr/bin/env python3

import json
import sys

def main():
    # 1. Read the hook input from stdin
    input_data = json.load(sys.stdin)

    # 2. Extract what you need
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # 3. Decide if this event is relevant to your check
    if not relevant(file_path):
        sys.exit(0)  # Not relevant — let it pass

    # 4. Run your validation logic
    violations = validate(file_path)

    # 5. Report results
    if violations:
        print(format_feedback(violations), file=sys.stderr)
        sys.exit(2)  # Block — Claude gets the feedback
    else:
        sys.exit(0)  # Pass — proceed normally

if __name__ == "__main__":
    main()
```

Five steps: read input, extract fields, check relevance, validate, report. Every validator script, from a simple regex check to a complex AST analysis, follows this skeleton.

## Step 1: Reading Input

The hook input arrives as JSON on stdin. Always use `json.load(sys.stdin)` — don't try to parse it as a string or read it line by line.

```python
import json
import sys

input_data = json.load(sys.stdin)
```

If you're writing the script in bash instead of Python, use `jq`:

```bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
```

The `// empty` in jq prevents errors when a field doesn't exist — it returns an empty string instead of `null`.

### Handling Missing Fields

Not every hook event includes every field. A Stop hook doesn't have `tool_input`. A PreToolUse for a Bash command doesn't have `file_path`. Always use `.get()` with defaults:

```python
# Safe — returns empty string if the field doesn't exist
file_path = input_data.get("tool_input", {}).get("file_path", "")

# Unsafe — crashes if tool_input is missing
file_path = input_data["tool_input"]["file_path"]
```

If your script crashes, Claude Code treats it as a non-blocking error (similar to any non-zero, non-2 exit code). The tool call proceeds, your validation is silently skipped, and you only see the error in verbose mode. Always handle missing fields gracefully.

## Step 2: Extracting What You Need

The fields you extract depend on the hook event and what you're checking:

**For PostToolUse/PreToolUse on Edit:**
```python
file_path = input_data.get("tool_input", {}).get("file_path", "")
old_string = input_data.get("tool_input", {}).get("old_string", "")
new_string = input_data.get("tool_input", {}).get("new_string", "")
```

**For PostToolUse/PreToolUse on Write:**
```python
file_path = input_data.get("tool_input", {}).get("file_path", "")
content = input_data.get("tool_input", {}).get("content", "")
```

**For PostToolUse/PreToolUse on Bash:**
```python
command = input_data.get("tool_input", {}).get("command", "")
```

**For Stop hooks:**
```python
last_message = input_data.get("last_assistant_message", "")
stop_hook_active = input_data.get("stop_hook_active", False)
transcript_path = input_data.get("transcript_path", "")
```

For PostToolUse validators that check files, you have two options:

1. **Read `tool_input.content`** (for Write) or use `tool_input.new_string` (for Edit) — this gives you exactly what Claude wrote, without a disk read.

2. **Read the file from disk using `file_path`** — after a PostToolUse fires, the file has already been written. This gives you the complete current file, including parts Claude didn't change.

Option 2 is usually better for design validation because you want to check the whole file, not just the changed portion. An edit might be fine in isolation but create a conflict with existing code in the same file.

## Step 3: Relevance Checks

Most validators only apply to certain files. A token checker is irrelevant for `.py` files. A component checker is irrelevant for test files. An import checker should skip the design system's own source files.

**Always check relevance first and exit 0 immediately for irrelevant files.** This keeps the validator fast and prevents false positives.

```python
from pathlib import Path

def is_relevant(file_path: str) -> bool:
    """Check if this file should be validated."""
    if not file_path:
        return False

    path = Path(file_path)

    # Only check UI-related file types
    if path.suffix not in {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss"}:
        return False

    # Skip test files
    if ".test." in path.name or ".spec." in path.name or "__tests__" in str(path):
        return False

    # Skip storybook files
    if ".stories." in path.name:
        return False

    # Skip the design system's own source files
    skip_dirs = {"components/ui", "components/primitives", "design-system/src"}
    if any(d in str(path) for d in skip_dirs):
        return False

    # Skip generated files
    if ".generated." in path.name or "dist/" in str(path) or "build/" in str(path):
        return False

    return True
```

The list of exclusions matters. If the validator fires on test files, Claude will spend tokens "fixing" test mocks to use design tokens, which is pointless. If it fires on the design system's own component files, it will block the creation of the very components it's trying to enforce.

Think carefully about the boundaries: What files should this rule apply to? What files should it never touch?

## Step 4: Validation Logic

This is where the design rules live. A few patterns cover most design validation needs.

### Pattern: Regex Line Scanner

The simplest pattern. Scan each line for patterns that violate a rule.

```python
import re

def scan_for_violations(content: str, file_path: str) -> list[dict]:
    violations = []

    for line_num, line in enumerate(content.splitlines(), 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue

        # Check each rule
        for pattern, message_template in RULES:
            match = re.search(pattern, line)
            if match:
                violations.append({
                    "line": line_num,
                    "match": match.group(),
                    "message": message_template.format(value=match.group()),
                    "file": file_path,
                })

    return violations
```

Good for: hardcoded colors, hardcoded pixel values, raw HTML elements, inline styles, deprecated class names.

Limitation: can't understand structure. A regex can find `<button` but can't tell if it's inside a JSX return or a string literal or a comment that the simple comment check missed.

### Pattern: Import Analyzer

Check what a file imports and flag missing or incorrect imports.

```python
import re

def check_imports(content: str, file_path: str) -> list[dict]:
    violations = []

    # Find all imports
    imports = set()
    for match in re.finditer(r"import\s+.*?from\s+['\"](.+?)['\"]", content):
        imports.add(match.group(1))

    # Check: if the file uses UI patterns, it should import from the design system
    uses_jsx = bool(re.search(r"<\w+[\s>]", content))
    imports_from_ds = any("components/ui" in imp for imp in imports)

    if uses_jsx and not imports_from_ds:
        # File has JSX but no design system imports — might be reinventing
        violations.append({
            "line": 0,
            "message": (
                "This file contains JSX but doesn't import any design system "
                "components. Consider whether existing components could be used."
            ),
            "file": file_path,
        })

    # Check for direct library imports that should go through the design system
    direct_imports = {
        "@radix-ui": "Import from '@/components/ui/' instead of directly from Radix.",
        "@headlessui": "Import from '@/components/ui/' instead of directly from Headless UI.",
        "react-icons": "Import from '@/components/ui/icon' instead of directly from react-icons.",
    }

    for lib, message in direct_imports.items():
        if any(lib in imp for imp in imports):
            violations.append({
                "line": 0,
                "message": message,
                "file": file_path,
            })

    return violations
```

Good for: ensuring the design system is the single import surface for UI primitives, catching people who reach past the design system to the underlying library.

### Pattern: File Content Analyzer

Check properties of the file as a whole, not individual lines.

```python
def check_file_structure(content: str, file_path: str) -> list[dict]:
    violations = []

    # Check: file shouldn't define both a component and inline styles
    has_component = bool(re.search(r"export\s+(?:default\s+)?function\s+\w+", content))
    has_style_object = bool(re.search(r"(?:const|let)\s+styles?\s*=\s*\{", content))

    if has_component and has_style_object:
        violations.append({
            "line": 0,
            "message": (
                "Component defines inline style objects. Use design tokens "
                "and utility classes instead, or move styles to a CSS module."
            ),
            "file": file_path,
        })

    # Check: component file shouldn't be excessively long (may need decomposition)
    line_count = content.count("\n")
    if has_component and line_count > 300:
        violations.append({
            "line": 0,
            "message": (
                f"Component file is {line_count} lines. Consider decomposing "
                f"into smaller, composable components."
            ),
            "file": file_path,
        })

    return violations
```

Good for: structural rules that apply to the file as a unit rather than individual lines.

### Pattern: Config-Driven Validation

The most maintainable approach for rules that change over time. The validation logic is generic; the rules come from a config file.

```python
import json
from pathlib import Path

def load_rules(config_path: str) -> list[dict]:
    """Load validation rules from a JSON config file."""
    path = Path(config_path)
    if not path.exists():
        return []
    return json.loads(path.read_text())

# rules.json:
# [
#   {
#     "pattern": "#[0-9a-fA-F]{3,8}",
#     "context": "style|className|color|background|border",
#     "message": "Hardcoded hex color. Use a design token: var(--color-*)",
#     "severity": "error",
#     "file_types": [".tsx", ".jsx", ".css"]
#   },
#   {
#     "pattern": "(?:margin|padding|gap):\\s*\\d+px",
#     "message": "Hardcoded pixel spacing. Use spacing tokens.",
#     "severity": "error",
#     "file_types": [".tsx", ".jsx", ".css"]
#   }
# ]
```

Good for: teams that want to add rules without modifying script code. A designer can add a rule to a JSON file without understanding Python.

## Step 5: Reporting Results

How you format the feedback determines whether Claude fixes things in one iteration or three.

### Exit Code Semantics

```python
sys.exit(0)   # Pass — tool call proceeds normally
sys.exit(2)   # Block — tool call is treated as failed, stderr goes to Claude
sys.exit(1)   # Error — tool call proceeds, stderr logged but not shown to Claude
```

Exit code 2 is the important one for validators. It tells Claude Code: "This tool call should be considered unsuccessful, and the message on stderr is why." Claude receives that message as feedback and acts on it.

Exit code 1 (and any other non-zero, non-2 code) means "the hook script itself errored." The tool call still succeeds, and your error message goes to the debug log, not to Claude. Use this distinction to differentiate between "the code has violations" (exit 2) and "the validator script crashed" (exit 1).

### The Structured JSON Alternative

For Stop hooks and some advanced PreToolUse scenarios, you can return structured JSON on stdout instead of using stderr + exit 2:

```python
import json

# For Stop hooks — sends Claude back to work
print(json.dumps({
    "ok": False,
    "reason": "Design token violations remain in src/Card.tsx"
}))
sys.exit(0)  # Note: exit 0, not exit 2. The JSON controls the decision.

# For PreToolUse hooks — deny with feedback
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "Use <Button> instead of raw <button>"
    }
}))
sys.exit(0)
```

When using JSON output, always exit 0. The JSON body controls the decision. Don't mix exit 2 with JSON — Claude Code ignores JSON when the exit code is 2.

### Formatting the Feedback Message

The feedback message is Claude's only guide for fixing the issue. Make it count.

**Template for per-violation feedback:**
```
{file_path}:
  - Line {line}: {description} — found `{value}`. {fix_instruction}.
```

**Template for file-level feedback:**
```
{description} in {file_path}. {fix_instruction}. See {reference} for details.
```

**Template for multi-file feedback (Stop hooks):**
```
Design audit found {count} issues across {file_count} files:

{file_path_1}:
  - {violation_1}
  - {violation_2}

{file_path_2}:
  - {violation_3}

Fix all violations. Refer to {reference} for available tokens and components.
```

Always end with a pointer to reference material if it exists. "See references/design-tokens.md" or "Check component-map.json" gives Claude a specific place to look for the correct values.

## Performance

Validators on PostToolUse run on *every* file edit. If Claude edits 40 files while building a page, each validator runs 40 times. Speed matters.

**Target: under 100ms per invocation for command handlers.**

Strategies:
- **Exit early for irrelevant files.** The relevance check (Step 3) should be the first thing that runs. Exiting in under 1ms for a `.py` file is free.
- **Read the file once.** Don't read the file multiple times for multiple checks. Read once, run all checks against the content string.
- **Avoid shelling out.** Don't call `npx prettier` or `eslint` from inside a PostToolUse validator — those cold-start times are measured in seconds. Use pure Python/bash logic.
- **Compile regexes once.** If you have many patterns, compile them at module load time, not inside the validation function.

```python
import re

# Compile once at module load
COMPILED_RULES = [
    (re.compile(pattern), message)
    for pattern, message in RAW_RULES
]

def validate(content):
    violations = []
    for regex, message in COMPILED_RULES:
        for match in regex.finditer(content):
            violations.append(...)
    return violations
```

For Stop hook handlers, speed is less critical since they run once per task, not per edit. A Stop hook that takes 2-5 seconds is fine. A PostToolUse handler that takes 2-5 seconds makes Claude feel sluggish.

## Testing Validators Locally

Always test your validator before deploying it in a hook. Pipe sample JSON to stdin:

```bash
# Test with a simulated Edit tool call
echo '{
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "src/components/SettingsPage.tsx",
    "old_string": "old code",
    "new_string": "new code"
  }
}' | python .claude/hooks/validate-tokens.py

echo "Exit code: $?"
```

```bash
# Test with a Write tool call
echo '{
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "src/components/NewCard.tsx",
    "content": "<div style=\"color: #ff0000\">test</div>"
  }
}' | python .claude/hooks/validate-tokens.py

echo "Exit code: $?"
```

```bash
# Test the Stop hook
echo '{
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "I finished building the page.",
  "transcript_path": "/tmp/test-transcript.jsonl",
  "session_id": "test-123"
}' | python .claude/hooks/stop-audit.py

echo "Exit code: $?"
```

Check three things:
1. **Exit code** — does it exit 0 for passing files and exit 2 for violations?
2. **Stderr output** — is the feedback message specific and actionable?
3. **Edge cases** — what happens with empty files, missing fields, non-UI files, the design system's own files?

## Common Mistakes

**Crashing on unexpected input.** If your script ever hits an unhandled exception, the hook fails silently and your validation is skipped. Wrap the main function in a try/except that exits 0 on any unexpected error. A validator that crashes is worse than no validator — it gives false confidence.

```python
def main():
    try:
        # ... validation logic ...
    except json.JSONDecodeError:
        sys.exit(0)  # Can't parse input — let it pass
    except Exception:
        sys.exit(0)  # Unknown error — let it pass, don't block Claude
```

**Reporting one violation at a time.** If a file has five violations and you only report the first one, Claude fixes it, the handler fires again, reports the second one, Claude fixes it, and so on for five cycles. Report all violations at once.

**Hardcoding project-specific paths.** Use `${CLAUDE_SKILL_DIR}` for skill-relative paths and `${CLAUDE_PROJECT_DIR}` for project-relative paths. Don't use `/Users/dan/myproject/src/components`.

**Checking files the validator shouldn't touch.** Test files, storybook files, the design system source, config files, markdown — make sure your relevance check excludes everything that isn't a consumer of the design system.

**Being too strict too early.** A validator that produces 50 violations on every existing file will overwhelm Claude and slow everything down. Start with the most impactful rules (hardcoded colors, raw HTML elements) and add more as the codebase comes into compliance.

**Forgetting to make the script executable.** On macOS/Linux, scripts need `chmod +x`. Claude Code can't run a script that isn't executable. Add this to your setup instructions.
