# Part 2: The Handler Taxonomy

A hook is an event — a moment in Claude Code's lifecycle where something just happened or is about to happen. A handler is what runs at that moment. The hook decides *when*. The handler decides *what*.

Claude Code supports four handler types. Each has different strengths, costs, and appropriate uses. Choosing the right handler type for a given design rule is the most important decision in this entire system.

## What Handlers Actually Receive

Before diving into the handler types, you need to understand what data they work with. This is the most common source of confusion.

**Claude has no awareness that hooks exist.** It doesn't prepare data for them, doesn't organize its output for them, and doesn't know they're running. Hooks are infrastructure that operates *around* Claude, not *with* it.

When Claude uses a tool — editing a file, writing a new file, running a bash command — Claude Code's tool system passes **structured JSON describing that tool call** to your handler on stdin. This isn't prose or "thoughts from the AI." It's a machine-generated data structure with specific fields.

### Tool-Related Hooks (PreToolUse, PostToolUse)

Every tool call has a predictable JSON schema. When Claude edits a file, your handler receives:

```json
{
  "session_id": "abc123",
  "cwd": "/Users/project",
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/Users/project/src/components/SettingsPage.tsx",
    "old_string": "<div className=\"card\">",
    "new_string": "<Card variant=\"outlined\">"
  },
  "tool_response": {
    "filePath": "/Users/project/src/components/SettingsPage.tsx",
    "success": true
  }
}
```

When Claude writes a new file, your handler receives:

```json
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/Users/project/src/components/NewModal.tsx",
    "content": "import React from 'react';\n\nexport function NewModal({ children }) {\n  return <div className=\"modal\">..."
  }
}
```

When Claude runs a bash command:

```json
{
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm run build",
    "description": "Build the project"
  }
}
```

The key insight: **your handler gets the file path and the exact code Claude wrote.** For Write calls, `tool_input.content` is the entire file. For Edit calls, you get `old_string` and `new_string`. You can also just read the file from disk using the `file_path` — after a PostToolUse hook fires, the file has already been written.

This is what makes command handlers so effective for design validation. You're not asking an LLM to evaluate code. You're running a Python script against an actual file with an actual path.

### The Stop Hook

When Claude finishes responding, the Stop hook gets different data:

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../abc123.jsonl",
  "stop_hook_active": false,
  "last_assistant_message": "I've finished building the settings page. Here's what I did..."
}
```

`last_assistant_message` is Claude's final text response — this *is* prose. `transcript_path` points to the full conversation log on disk if you need more context. The Stop hook does **not** receive the full conversation inline — your script has to read the transcript file if it needs that.

### How Prompt and Agent Handlers Get This Data

Prompt and agent handlers receive the same JSON, injected into their prompt via the `$ARGUMENTS` placeholder:

```json
{
  "type": "prompt",
  "prompt": "Check if this code uses design tokens properly. $ARGUMENTS"
}
```

`$ARGUMENTS` is replaced with the full hook input JSON. So the model evaluating your prompt handler sees the tool name, file path, and code content — exactly what a command handler would parse with `jq` or Python. The difference is that the model interprets it with judgment instead of regex.

For agent handlers, the subagent gets the same JSON and can *also* use tools (Read, Grep, Glob) to explore beyond what's in the input.

### Common Fields All Hooks Receive

Every hook event includes these base fields:

| Field | What it contains |
|---|---|
| `session_id` | Unique session identifier |
| `cwd` | Current working directory when the hook fired |
| `transcript_path` | Path to the conversation transcript file on disk |
| `hook_event_name` | Which event triggered this hook |
| `permission_mode` | Current permission mode (`default`, `acceptEdits`, etc.) |

Event-specific fields are added on top of these. PreToolUse/PostToolUse add `tool_name` and `tool_input`. Stop adds `last_assistant_message` and `stop_hook_active`. SessionStart adds `source` (whether it's a fresh start, resume, or post-compaction restart). The full schema for each event is in the [Hooks reference](https://code.claude.com/docs/en/hooks).

### Why This Matters for Design Validation

Because the input is structured and predictable, your validator scripts can be precise:

- **Token validator**: Parse `tool_input.file_path`, read the file, regex-scan for hardcoded colors. You know exactly which file changed.
- **Component checker**: Parse `tool_input.file_path`, check if it's a `.tsx` file, scan for raw HTML elements. You don't need Claude to tell you what it did.
- **New component gatekeeper** (PreToolUse on Write): Parse `tool_input.file_path`, check if it's creating a file in `components/`. Block it before it happens.

The handler doesn't need to ask Claude what it did. It can see for itself.

---

## Command Handlers

**What they are:** A shell command or script that runs deterministically. No LLM involved. The script reads JSON from stdin (describing what Claude just did or is about to do), makes a decision with code, and returns the result via exit codes and stdout/stderr.

**Cost:** Zero tokens. The script runs outside Claude's context entirely.

**Speed:** Milliseconds to low seconds, depending on script complexity.

**When to use them for design work:**

Command handlers are right for any rule you can express as code. The question to ask: *"Could I write a regex, an AST parser, or a file check that determines pass/fail?"* If yes, it's a command handler.

### Example: Token Validator

This script runs after every file edit and checks that no hardcoded colors, font sizes, or spacing values appear in the output. Everything must come from design tokens.

```python
#!/usr/bin/env python3
"""Validate that all style values use design tokens, not hardcoded values."""

import json
import sys
import re

# Hardcoded values that should be tokens
HARDCODED_PATTERNS = [
    # Hex colors
    (r'["\']#[0-9a-fA-F]{3,8}["\']', "hardcoded hex color"),
    (r':\s*#[0-9a-fA-F]{3,8}', "hardcoded hex color in style"),
    # Pixel values for spacing (allow 0px and 1px as exceptions)
    (r'(?:margin|padding|gap).*?:\s*[2-9]\d*px', "hardcoded spacing value"),
    (r'(?:margin|padding|gap).*?:\s*[1-9]\d{2,}px', "hardcoded spacing value"),
    # Font sizes as raw pixels
    (r'font-size:\s*\d+px', "hardcoded font size"),
    # RGB/RGBA values
    (r'rgba?\(\s*\d+', "hardcoded RGB color"),
]

# Files to check
STYLE_EXTENSIONS = {'.css', '.scss', '.tsx', '.jsx', '.vue', '.svelte'}


def validate_file(file_path: str) -> list[dict]:
    """Check a file for hardcoded style values."""
    from pathlib import Path

    path = Path(file_path)
    if path.suffix not in STYLE_EXTENSIONS:
        return []

    if not path.exists():
        return []

    violations = []
    content = path.read_text()

    for line_num, line in enumerate(content.splitlines(), 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            continue

        for pattern, description in HARDCODED_PATTERNS:
            matches = re.finditer(pattern, line)
            for match in matches:
                violations.append({
                    "line": line_num,
                    "column": match.start(),
                    "value": match.group(),
                    "description": description,
                    "text": stripped,
                })

    return violations


def main():
    input_data = json.load(sys.stdin)

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    violations = validate_file(file_path)

    if not violations:
        sys.exit(0)

    # Format violations as actionable feedback
    messages = []
    for v in violations:
        messages.append(
            f"Line {v['line']}: {v['description']} — found `{v['value']}`. "
            f"Use a design token instead."
        )

    feedback = (
        f"Design token violations in {file_path}:\n"
        + "\n".join(f"  - {m}" for m in messages)
        + "\n\nReplace hardcoded values with tokens from your design system. "
        + "Check references/design-tokens.md for available tokens."
    )

    print(feedback, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
```

The hook configuration that runs this after every edit:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_SKILL_DIR}/scripts/validate-tokens.py"
          }
        ]
      }
    ]
  }
}
```

Or in a skill's frontmatter:

```yaml
---
name: design-enforcer
description: Enforces design system consistency when building UI
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "python ${CLAUDE_SKILL_DIR}/scripts/validate-tokens.py"
---
```

### Example: Component Import Checker

This script verifies that raw HTML elements aren't used when a design system component exists.

```python
#!/usr/bin/env python3
"""Check that design system components are used instead of raw HTML."""

import json
import sys
import re
from pathlib import Path

# Map raw HTML patterns to the design system component that should be used
COMPONENT_MAP = {
    r'<button[\s>]': "Use <Button> from '@/components/ui/button'",
    r'<input[\s>]': "Use <Input> from '@/components/ui/input'",
    r'<select[\s>]': "Use <Select> from '@/components/ui/select'",
    r'<textarea[\s>]': "Use <Textarea> from '@/components/ui/textarea'",
    r'<dialog[\s>]': "Use <Dialog> from '@/components/ui/dialog'",
    r'<a[\s>](?!.*href=["\']#)': "Use <Link> from '@/components/ui/link'",
    r'<table[\s>]': "Use <DataTable> from '@/components/ui/data-table'",
}

# Only check component/page files, not the design system components themselves
COMPONENT_DIRS = {'components/ui', 'components/primitives'}


def main():
    input_data = json.load(sys.stdin)
    file_path = input_data.get("tool_input", {}).get("file_path", "")

    if not file_path:
        sys.exit(0)

    path = Path(file_path)

    # Don't check the design system's own component files
    for component_dir in COMPONENT_DIRS:
        if component_dir in str(path):
            sys.exit(0)

    # Only check TSX/JSX files
    if path.suffix not in {'.tsx', '.jsx'}:
        sys.exit(0)

    if not path.exists():
        sys.exit(0)

    content = path.read_text()
    violations = []

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('{/*'):
            continue

        for pattern, replacement in COMPONENT_MAP.items():
            if re.search(pattern, line, re.IGNORECASE):
                violations.append(f"Line {line_num}: raw HTML element found. {replacement}")

    if not violations:
        sys.exit(0)

    feedback = (
        f"Component violations in {file_path}:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nUse design system components instead of raw HTML elements. "
        + "This ensures consistent styling, accessibility, and behavior."
    )

    print(feedback, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
```

### What Makes a Good Command Handler

The feedback a command handler gives Claude is the single most important factor in whether the correction loop works. Bad feedback creates confusion and wasted tokens. Good feedback creates instant, correct fixes.

**Bad feedback:**
```
Error: invalid color value
```

Claude doesn't know which line, which file, what the value was, or what to replace it with. It will guess, possibly introducing new violations.

**Good feedback:**
```
Design token violations in src/components/SettingsPage.tsx:
  - Line 12: hardcoded hex color — found `#ffffff`. Use a design token instead.
  - Line 34: hardcoded spacing value — found `padding: 10px`. Use a multiple of 8 (e.g., 8px, 16px) or a spacing token.

Replace hardcoded values with tokens from your design system.
Check references/design-tokens.md for available tokens.
```

Claude knows exactly what to fix, where to fix it, and what to replace it with. The correction takes one edit, not three rounds of guessing.

Principles for command handler feedback:

1. **Include the file path and line number.** Always.
2. **Show the offending value.** Don't just say "wrong" — show what was wrong.
3. **State the fix, not just the problem.** "Use `var(--surface-primary)`" not "invalid color."
4. **Point to reference material.** If there's a token file or component catalog, name it.
5. **Keep it structured.** One violation per line. Claude parses structured text much better than paragraphs.

### Command Handler Limitations

Command handlers can't:

- Understand *intent*. They can catch `<button>` but not "this layout doesn't feel right."
- Compare across files. They see one event at a time — the file that was just edited.
- Make judgment calls. The rule is either violated or it isn't.

When you need any of these, you need a different handler type.

---

## Prompt Handlers

**What they are:** A single-turn LLM call. You write a natural language prompt. When the hook fires, Claude Code sends your prompt plus the hook's input data to a fast model (Haiku by default, configurable) and gets back a yes/no decision with an optional reason.

**Cost:** A few hundred tokens per invocation. Cheap, but not free.

**Speed:** 1-3 seconds typically.

**When to use them for design work:**

Prompt handlers are right when the rule requires *judgment* but doesn't require reading other files. The question to ask: *"Can I describe what's wrong in a sentence, and could a person evaluate it just by looking at the code Claude just wrote?"* If yes, a prompt handler works.

### Example: Layout Coherence Check

After Claude finishes a task, check whether the layout follows established patterns:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Review the code changes in this session. Check: (1) Do flex/grid layouts follow a consistent pattern — e.g., not mixing flexbox and grid for the same type of layout within the same page? (2) Is the visual hierarchy clear — headings, subheadings, body text, captions used in descending order? (3) Are interactive elements (buttons, links, inputs) visually distinguishable from static content? If any of these fail, respond with {\"ok\": false, \"reason\": \"specific description of what's inconsistent and how to fix it\"}. If all pass, respond with {\"ok\": true}."
          }
        ]
      }
    ]
  }
}
```

### Example: Naming Convention Review

Before Claude writes a file, check that component and class naming follows conventions:

```yaml
# In skill frontmatter
hooks:
  PreToolUse:
    - matcher: "Write"
      hooks:
        - type: prompt
          prompt: >
            Check the file about to be written. Verify: component names use
            PascalCase, CSS classes use kebab-case or the project's utility
            class convention, and file names match the component they export
            (e.g., UserProfile.tsx exports UserProfile). If naming is
            inconsistent, respond with {"ok": false, "reason": "..."}.
```

### When Prompt Handlers Beat Command Handlers

The line between "I can write code for this" and "I need judgment" is sometimes blurry. Here's a practical test:

| Rule | Command handler? | Prompt handler? |
|---|---|---|
| "Colors must be tokens" | Yes — regex match | Overkill |
| "Spacing must be 8px multiples" | Yes — math check | Overkill |
| "Layout should feel consistent" | Can't express in code | Yes |
| "Typography hierarchy should be clear" | Partially (can check tag order) | Better — understands visual weight |
| "Component naming follows conventions" | Partially (can regex PascalCase) | Better — understands edge cases |
| "This looks like a card, use the Card component" | Very hard to express in code | Yes — understands intent |

If you find yourself writing a 200-line script full of heuristics and special cases, a one-sentence prompt handler might do the job better. If you find yourself writing a prompt for something that has a clear binary answer, a five-line script is faster and cheaper.

### Prompt Handler Limitations

Prompt handlers:

- Can't read other files. They only see the hook's input data (what Claude just did or is about to do).
- Make a single judgment call. They can't explore, investigate, or do multi-step reasoning.
- Are probabilistic. Two runs might give different answers on edge cases. This is fine for judgment calls — it's a problem if you want deterministic enforcement.
- Cost tokens every time they fire. A prompt handler on `PostToolUse` with an `Edit|Write` matcher runs on every single file edit. If Claude edits 30 files, that's 30 Haiku calls.

When you need to compare against other files or do multi-step verification, you need an agent handler.

---

## Agent Handlers

**What they are:** A multi-turn subagent with access to tools — it can read files, grep the codebase, run commands, and reason across multiple steps before returning a decision. Same `{"ok": true/false, "reason": "..."}` response format as prompt handlers, but with much more capability.

**Cost:** Hundreds to thousands of tokens, depending on how many tool calls the agent makes.

**Speed:** 5-60+ seconds, depending on complexity. Default timeout is 60 seconds.

**When to use them for design work:**

Agent handlers are right when enforcement requires *context from elsewhere in the codebase*. The question to ask: *"Does checking this rule require reading files other than the one Claude just edited?"* If yes, you likely need an agent handler.

### Example: Cross-File Composition Audit

The most valuable agent handler for design work. When Claude finishes a task, an agent reads the existing components and verifies the new code composes them correctly:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "agent",
            "prompt": "Audit the files modified in this session for design system compliance. For each modified file: (1) Read the project's component directory to identify available design system components. (2) Check if any raw HTML elements are used where a design system component exists. (3) For each design system component that IS used, read its source to verify the props are used correctly — not just that the component is imported, but that it's configured properly. (4) Check that the composition pattern (how components are arranged relative to each other) matches established patterns in similar pages. Report any violations. $ARGUMENTS",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

This is something no command handler or prompt handler can do — it requires reading the component source files, understanding their APIs, and comparing usage across the codebase.

### Example: Pattern Consistency Check

Before Claude creates a new component file, an agent checks whether a similar component already exists:

```yaml
hooks:
  PreToolUse:
    - matcher: "Write"
      hooks:
        - type: agent
          prompt: >
            The agent is about to create a new file. Check if this file
            appears to be a new UI component. If it is: (1) Search the
            existing components directory for components with similar names
            or purposes. (2) If a similar component exists, respond with
            {"ok": false, "reason": "A similar component already exists at
            [path]. Consider using or extending it instead of creating a
            new one."} (3) If no similar component exists, respond with
            {"ok": true}. $ARGUMENTS
          timeout: 30
```

This is the **composition-over-creation enforcer** — it blocks Claude from creating new components without first checking what already exists.

### When Agent Handlers Are Worth the Cost

Agent handlers are expensive. A single invocation might use more tokens than 50 command handler runs. Use them where the cost is justified:

**Worth it:**
- Cross-file consistency checks (comparing new code against existing patterns)
- Component API compliance (reading a component's props and verifying correct usage)
- Pre-creation gatekeeping (searching for existing alternatives before allowing new files)
- End-of-task audits (comprehensive review after all edits are done, runs once)

**Not worth it:**
- Checking individual token values (command handler does this for free)
- Validating file naming conventions (command handler or prompt handler is sufficient)
- Anything that runs on every single edit (the cost adds up fast)

The best pattern: use command handlers on `PostToolUse` for per-edit enforcement (cheap, fast, every edit), and reserve agent handlers for `Stop` hooks (expensive, thorough, runs once at the end).

### Agent Handler Limitations

- Expensive. Every tool call the agent makes costs tokens.
- Slow. A 30-second agent handler on `PostToolUse` would make Claude feel sluggish. Use them on `Stop` or `PreToolUse` where a pause is acceptable.
- Can create loops. If a `Stop` agent handler returns `{"ok": false}`, Claude keeps working. If the agent handler keeps finding issues, the session can loop. Always check `stop_hook_active` in Stop hooks or set a reasonable `timeout`.

---

## HTTP Handlers

**What they are:** A POST request to an HTTP endpoint. The endpoint receives the same JSON a command handler would get on stdin, and returns a decision in the response body. The handler communicates over the network rather than running a local process.

**Cost:** Depends on the service. Zero LLM tokens from Claude's perspective.

**Speed:** Depends on the endpoint. Network latency is the floor.

**When to use them for design work:**

HTTP handlers are right when the validation logic lives outside the local machine — a shared team service, a visual regression API, or a design system compliance server.

### Example: Visual Regression Check

Post a screenshot to a visual regression service after Claude edits a component:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "http",
            "url": "http://localhost:9222/api/design-check",
            "headers": {
              "Authorization": "Bearer $DESIGN_API_TOKEN"
            },
            "allowedEnvVars": ["DESIGN_API_TOKEN"]
          }
        ]
      }
    ]
  }
}
```

### Example: Shared Team Design Audit

Post every file edit to a team-wide design compliance service that tracks drift over time:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "http",
            "url": "https://internal.company.com/design-audit/check",
            "headers": {
              "X-Project": "my-app",
              "Authorization": "Bearer $AUDIT_TOKEN"
            },
            "allowedEnvVars": ["AUDIT_TOKEN"]
          }
        ]
      }
    ]
  }
}
```

The service could aggregate violations across the team, track design drift over time, and block merges when compliance drops below a threshold.

### When HTTP Handlers Make Sense

For most individual designers, HTTP handlers are overkill. They shine when:

- A team shares validation logic and wants a single source of truth
- The validation requires services not available locally (GPU-powered visual comparison, screenshot rendering, etc.)
- You want an audit trail that persists across sessions and developers
- The validation logic changes frequently and you don't want to update scripts on every machine

---

## Choosing the Right Handler: The Decision Tree

Start here for any design rule you want to enforce:

```
Can you express the rule as code?
├── YES: Can a regex, AST check, or file read determine pass/fail?
│   ├── YES → Command handler
│   └── MOSTLY, but edge cases need judgment → Command handler for the 80%,
│       prompt handler for the rest
│
├── NO: The rule requires judgment.
│   ├── Can it be evaluated from the hook input alone (just the code Claude wrote)?
│   │   ├── YES → Prompt handler
│   │   └── NO: It needs to read other files or check the codebase.
│   │       └── Agent handler
│   │
│   └── Does the logic live on an external service?
│       └── HTTP handler
```

For a typical design system, the breakdown is roughly:

- **60-70% command handlers**: token validation, spacing checks, import enforcement, file naming, accessibility baselines
- **15-20% prompt handlers**: layout coherence, visual hierarchy, naming judgment calls
- **10-15% agent handlers**: cross-file consistency, composition audits, pre-creation gatekeeping
- **0-5% HTTP handlers**: visual regression, team-wide compliance tracking

Most of your enforcement should be deterministic. The expensive handlers handle the genuinely ambiguous cases.

---

## Handler Types vs. Skill-Instructed Scripts

Everything above describes handlers that run inside hooks — they fire automatically when an event occurs. But there's a parallel track: scripts and checks that Claude runs because the SKILL.md tells it to.

The difference matters:

| | Hook handler | Skill-instructed |
|---|---|---|
| **Trigger** | Automatic — fires on lifecycle event | Claude decides — reads instruction, chooses when to run it |
| **Token cost of triggering** | Zero — hook infrastructure handles it | Some — Claude reads the instruction and invokes the script |
| **Reliability** | 100% — always fires if matcher matches | High but not guaranteed — Claude might skip it under token pressure |
| **Flexibility** | Fixed — same check every time | Contextual — Claude can pass different arguments, skip when irrelevant |
| **Good for** | Rules that must always be enforced | Checks that are situational or need Claude's judgment about *when* to run |

A complete design enforcement system uses both:

- **Hook handlers** for non-negotiable rules: "Every edit must pass token validation."
- **Skill-instructed scripts** for contextual checks: "When building a form, run the form accessibility audit." "Before presenting the final result, run the full-page composition check."

The SKILL.md instruction for a script looks like this:

```markdown
## Before completing any UI task

Run the full design audit on all files you modified:

\`\`\`bash
python ${CLAUDE_SKILL_DIR}/scripts/audit-page.py <file1> <file2> ...
\`\`\`

Fix all violations before presenting the result to the user.
```

This costs tokens (Claude reads the instruction and decides to run it), but it gives Claude flexibility to pass the right files as arguments and interpret nuanced output.

The next parts of this guide cover where handlers run (Part 3), how feedback loops work (Part 4), and the specific patterns for composition enforcement (Part 5).
