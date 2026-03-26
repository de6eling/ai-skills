# Part 7: Worked Example

This part walks through a complete, self-contained skill that enforces design system consistency. It uses all four handler types, demonstrates both always-on and skill-scoped hooks, and includes skill-instructed scripts for on-demand checks.

The example assumes a React + Tailwind project using a shadcn/ui-style component library. The patterns adapt to any component-based framework — the principles are the same regardless of whether you're using Vue, Svelte, or vanilla web components.

## The Skill Structure

```
.claude/
├── settings.json                    # Always-on hooks (project-level)
├── config/
│   ├── component-map.json           # Component replacement map
│   └── design-rules.json            # Token and spacing rules
└── skills/
    └── design-system-enforcer/
        ├── SKILL.md                  # Skill definition + scoped hooks
        ├── scripts/
        │   ├── validate-tokens.py        # Token validation (always-on)
        │   ├── check-imports.py          # Import enforcement (always-on)
        │   ├── check-composition.py      # Prop/pattern validation (always-on)
        │   ├── component-inventory.py    # Proactive inventory (skill-instructed)
        │   └── full-audit.py             # Comprehensive audit (skill-instructed)
        ├── config/
        │   └── component-map.json        # Component replacement map
        └── references/
            ├── design-tokens.md          # Token reference
            └── composition-patterns.md   # Pattern reference
```

## The Always-On Hooks

These go in `.claude/settings.json` at the project root. Everyone who clones the repo gets them. They run on every file edit, regardless of what skill is active.

```json
{
  "permissions": {
    "allow": [
      "Bash(python *)",
      "Edit",
      "Write"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/skills/design-system-enforcer/scripts/validate-tokens.py\""
          },
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/skills/design-system-enforcer/scripts/check-imports.py\""
          },
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/skills/design-system-enforcer/scripts/check-composition.py\""
          }
        ]
      }
    ]
  }
}
```

Three command handlers run in parallel after every Edit or Write. Each checks one category of violation:

1. **validate-tokens.py** — no hardcoded colors, spacing, font sizes, or shadows
2. **check-imports.py** — no raw HTML when a design system component exists
3. **check-composition.py** — no style overrides on controlled components, correct compound component usage

If any of them exit 2, Claude gets the feedback and corrects before proceeding.

## The Skill Definition

`.claude/skills/design-system-enforcer/SKILL.md`:

```yaml
---
name: design-system-enforcer
description: >
  Enforces design system consistency when building UI components and pages.
  Activates when creating components, building pages, converting Figma designs,
  or any front-end implementation task. Ensures existing components are used
  correctly through composition rather than reinventing them.
hooks:
  PreToolUse:
    - matcher: "Write"
      hooks:
        - type: agent
          prompt: >
            Claude is about to create a new file. Examine the file_path in
            $ARGUMENTS.

            If the path is inside a components directory (src/components/,
            components/, ui/, shared/):

            1. Search existing component directories for similar components.
            2. Read any matches to understand their capabilities.
            3. If a similar component exists, respond:
               {"ok": false, "reason": "Existing component at [path] provides
               [capabilities]. Use or extend it instead. If a new component is
               truly needed, explain in a code comment why the existing one is
               insufficient."}
            4. If no match exists, respond: {"ok": true}

            If the path is NOT a component directory, respond: {"ok": true}
          timeout: 30
  Stop:
    - hooks:
        - type: agent
          prompt: >
            Audit the UI files modified in this session for design system
            compliance. $ARGUMENTS

            Steps:
            1. Identify modified UI files (.tsx, .jsx) from recent tool use.
            2. For each file, read it and check:
               a. Components are composed following project patterns
               b. Layout approach (grid/flex, gap values, container widths)
                  matches similar existing pages
               c. No components are used in unusual or undocumented ways
            3. Search for 1-2 similar pages to compare layout patterns.
            4. If inconsistencies found, respond:
               {"ok": false, "reason": "[specific issues and how to fix them]"}
            5. If consistent, respond: {"ok": true}

            Focus on composition patterns, not tokens or imports (those are
            handled by per-edit validators).
          timeout: 120
        - type: prompt
          prompt: >
            Review the session's last message. Check if the implementation
            described uses appropriate semantic HTML structure — headings
            follow h1>h2>h3 order, lists are used for list content, nav is
            used for navigation, main/section/article for content areas.
            If semantic structure is poor, respond:
            {"ok": false, "reason": "[what to fix]"}
---

# Design System Enforcer

You are building UI in a project with an established design system. Your primary
job is to **compose existing components**, not create new ones.

## Before Starting Any UI Work

Run the component inventory to see what's available:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/component-inventory.py
```

Plan your implementation using these existing components before writing any code.

## Core Principles

1. **Compose, don't create.** Use existing components for every UI element.
   Only create a new component if nothing in the inventory serves the purpose.

2. **Use the variant system.** Components have variants (size, color, style)
   for a reason. Use `<Button variant="secondary">`, not `<Button className="bg-gray-200">`.

3. **Follow established layout patterns.** Before building a page layout,
   read a similar existing page and match its grid/flex structure, gap values,
   and container approach.

4. **Tokens for everything.** All colors, spacing, typography, shadows, and
   border-radii come from design tokens. No hardcoded values.

5. **Compound components stay compound.** Card needs CardHeader + CardContent.
   Dialog needs DialogContent. Table needs TableHeader + TableBody. Don't
   skip the pieces.

## When You Need a New Component

If the inventory doesn't have what you need:

1. Check if an existing component can be extended with a new variant
2. Check if composition of existing components achieves the goal
3. Only if neither works, create a new component — and document why

## Before Completing Your Work

Run the full design audit on all files you modified:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/full-audit.py
```

Fix any violations before presenting results to the user.

## Reference

- For available tokens: see [design-tokens.md](references/design-tokens.md)
- For composition patterns: see [composition-patterns.md](references/composition-patterns.md)
```

## The Skill-Scoped Hooks in Action

When this skill activates (either via `/design-system-enforcer` or automatically when Claude detects UI work), three additional hooks register:

1. **PreToolUse agent handler on Write** — the component creation gatekeeper. Before Claude can create any file in a components directory, an agent searches for existing alternatives. This is the composition-over-creation enforcer.

2. **Stop agent handler** — the cross-file consistency audit. When Claude finishes, an agent reads the modified files, compares layout patterns against similar pages, and reports inconsistencies.

3. **Stop prompt handler** — a semantic HTML check. Quick and cheap, verifies heading order and semantic element usage. Runs in parallel with the agent handler.

These hooks are more expensive than the always-on command handlers, but they only run during active design work — not when someone is editing a backend API route.

## The Reference Files

### `references/design-tokens.md`

```markdown
# Design Tokens

## Colors

### Semantic Colors (use these)
- `--color-primary` / `text-primary` / `bg-primary` — Brand blue
- `--color-secondary` / `text-secondary` / `bg-secondary` — Muted gray
- `--color-destructive` / `text-destructive` / `bg-destructive` — Error red
- `--color-success` / `text-success` / `bg-success` — Confirmation green
- `--color-warning` / `text-warning` / `bg-warning` — Caution amber

### Surface Colors
- `--surface-primary` / `bg-surface-primary` — Main background (white/dark)
- `--surface-secondary` / `bg-surface-secondary` — Card background
- `--surface-tertiary` / `bg-surface-tertiary` — Input background

### Border Colors
- `--border-primary` / `border-primary` — Default border
- `--border-secondary` / `border-secondary` — Subtle divider

## Spacing

Base unit: 4px. Use multiples of the base unit.

| Token | Value | Tailwind |
|-------|-------|----------|
| `--space-1` | 4px | `p-1`, `m-1`, `gap-1` |
| `--space-2` | 8px | `p-2`, `m-2`, `gap-2` |
| `--space-3` | 12px | `p-3`, `m-3`, `gap-3` |
| `--space-4` | 16px | `p-4`, `m-4`, `gap-4` |
| `--space-6` | 24px | `p-6`, `m-6`, `gap-6` |
| `--space-8` | 32px | `p-8`, `m-8`, `gap-8` |

## Typography

| Role | Token | Tailwind |
|------|-------|----------|
| Page title | `--text-2xl` | `text-2xl font-bold` |
| Section heading | `--text-xl` | `text-xl font-semibold` |
| Card title | `--text-lg` | `text-lg font-medium` |
| Body | `--text-base` | `text-base` |
| Caption | `--text-sm` | `text-sm text-muted-foreground` |
| Fine print | `--text-xs` | `text-xs text-muted-foreground` |

## Shadows

| Token | Usage |
|-------|-------|
| `--shadow-sm` / `shadow-sm` | Cards, dropdowns |
| `--shadow-md` / `shadow-md` | Modals, popovers |
| `--shadow-lg` / `shadow-lg` | Dialogs |

## Border Radius

| Token | Usage |
|-------|-------|
| `--radius-sm` / `rounded-sm` | Inputs, badges |
| `--radius-md` / `rounded-md` | Cards, buttons |
| `--radius-lg` / `rounded-lg` | Dialogs, large containers |
| `--radius-full` / `rounded-full` | Avatars, pills |
```

### `references/composition-patterns.md`

```markdown
# Composition Patterns

## Page Layout

Standard page structure:

```tsx
<div className="container mx-auto py-8 space-y-8">
  <div>
    <h1 className="text-2xl font-bold">Page Title</h1>
    <p className="text-muted-foreground">Page description</p>
  </div>

  {/* Content sections */}
</div>
```

- Container: `container mx-auto` (max-width controlled by Tailwind config)
- Page padding: `py-8` (32px vertical)
- Section spacing: `space-y-8` (32px between sections)

## Card Grid

For groups of cards (dashboards, settings, overviews):

```tsx
<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
  <Card>
    <CardHeader>
      <CardTitle>Title</CardTitle>
      <CardDescription>Description</CardDescription>
    </CardHeader>
    <CardContent>
      {/* Content */}
    </CardContent>
  </Card>
  {/* More cards */}
</div>
```

- Always 1 column on mobile, 2 on medium screens
- Gap: `gap-4` (16px)
- Each card follows the Card compound pattern

## Form Layout

For settings and input forms:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Section Name</CardTitle>
    <CardDescription>What this section controls</CardDescription>
  </CardHeader>
  <CardContent className="space-y-4">
    <div className="space-y-2">
      <Label htmlFor="field-name">Field Label</Label>
      <Input id="field-name" />
      <p className="text-sm text-muted-foreground">Helper text</p>
    </div>
    {/* More fields */}
  </CardContent>
  <CardFooter>
    <Button>Save Changes</Button>
  </CardFooter>
</Card>
```

- Each form section is a Card
- Field spacing: `space-y-4` (16px)
- Label-to-input spacing: `space-y-2` (8px)
- Helper text: `text-sm text-muted-foreground`
- Actions in CardFooter

## Data Display

For tables and lists:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Data Title</CardTitle>
  </CardHeader>
  <CardContent>
    <DataTable columns={columns} data={data} />
  </CardContent>
</Card>
```

- Tables always wrapped in Card
- Use DataTable for sortable/filterable data
- Use simple Table for static data
```

## The Full Audit Script

`scripts/full-audit.py` — the skill-instructed comprehensive check that runs before presenting results:

```python
#!/usr/bin/env python3
"""
Full design audit — runs all validators against recently modified UI files.

This is a skill-instructed script, not a hook handler. The SKILL.md tells
Claude to run it before completing a task. It produces a human-readable
report that Claude uses to make final corrections.
"""

import subprocess
import sys
import re
from pathlib import Path


def get_modified_ui_files() -> list[str]:
    """Find recently modified UI files via git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        staged = result.stdout.strip().splitlines() if result.stdout.strip() else []

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, timeout=10,
        )
        unstaged = result.stdout.strip().splitlines() if result.stdout.strip() else []

        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=10,
        )
        untracked = result.stdout.strip().splitlines() if result.stdout.strip() else []

        all_files = set(staged + unstaged + untracked)
        ui_extensions = {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss"}

        return [
            f for f in all_files
            if Path(f).suffix in ui_extensions
            and ".test." not in f
            and ".spec." not in f
            and ".stories." not in f
        ]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def check_tokens(content: str, file_path: str) -> list[str]:
    """Check for hardcoded style values."""
    violations = []
    patterns = [
        (r'["\']#[0-9a-fA-F]{3,8}["\']', "hardcoded hex color"),
        (r':\s*#[0-9a-fA-F]{3,8}', "hardcoded hex color"),
        (r'(?:margin|padding|gap).*?:\s*[2-9]\d*px', "hardcoded spacing"),
        (r'font-size:\s*\d+px', "hardcoded font size"),
        (r'rgba?\(\s*\d+', "hardcoded RGB color"),
        (r'box-shadow:\s*[^v]', "hardcoded shadow (use shadow token)"),
    ]

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        for pattern, desc in patterns:
            if re.search(pattern, line):
                violations.append(f"  Line {line_num}: {desc}")
                break  # One violation per line is enough

    return violations


def check_raw_html(content: str, file_path: str) -> list[str]:
    """Check for raw HTML elements that should be components."""
    violations = []
    raw_elements = {
        "<button": "<Button>",
        "<input": "<Input>",
        "<select": "<Select>",
        "<textarea": "<Textarea>",
        "<dialog": "<Dialog>",
        "<table": "<DataTable> or <Table>",
    }

    # Skip design system source files
    if "components/ui" in file_path or "components/primitives" in file_path:
        return []

    for line_num, line in enumerate(content.splitlines(), 1):
        for raw, replacement in raw_elements.items():
            if raw in line.lower():
                violations.append(f"  Line {line_num}: raw `{raw}` — use {replacement}")

    return violations


def check_style_overrides(content: str, file_path: str) -> list[str]:
    """Check for className/style on controlled components."""
    violations = []
    controlled = ["Button", "Badge", "Input", "Select", "Switch", "Checkbox"]

    for line_num, line in enumerate(content.splitlines(), 1):
        for comp in controlled:
            if re.search(rf"<{comp}\s[^>]*(className|style)\s*=", line):
                violations.append(
                    f"  Line {line_num}: style override on <{comp}> — use variant props"
                )

    return violations


def main():
    files = get_modified_ui_files()

    if not files:
        print("No modified UI files found. Audit complete.")
        sys.exit(0)

    total_violations = 0
    report_sections = []

    for file_path in sorted(files):
        path = Path(file_path)
        if not path.exists():
            continue

        content = path.read_text()
        file_violations = []

        file_violations.extend(check_tokens(content, file_path))
        file_violations.extend(check_raw_html(content, file_path))
        file_violations.extend(check_style_overrides(content, file_path))

        if file_violations:
            total_violations += len(file_violations)
            report_sections.append(f"\n### {file_path}\n" + "\n".join(file_violations))

    # Output report
    print(f"# Design Audit Report\n")
    print(f"Checked {len(files)} files.")

    if total_violations == 0:
        print("All files pass design system validation.")
    else:
        print(f"Found **{total_violations} violations** across {len(report_sections)} files:")
        for section in report_sections:
            print(section)
        print(f"\n---")
        print(f"Fix all violations before presenting the result.")
        print(f"Refer to references/design-tokens.md for available tokens.")

    sys.exit(0)  # Always exit 0 — this is informational, not a hook blocker


if __name__ == "__main__":
    main()
```

This script always exits 0 because it's skill-instructed, not a hook handler. It produces a report that Claude reads and acts on. The SKILL.md instruction "fix any violations before presenting results" is what drives the correction — the script just provides the information.

## How It All Plays Out

Here's a realistic session trace showing the entire system in action.

**User:** "Build a user preferences page. It should have sections for notification settings, privacy settings, and account details."

**Claude activates `design-system-enforcer` skill** (description matches "build a page").

**Claude runs component inventory** (skill-instructed):
```
Found 14 components: Button, Card, CardHeader, CardContent, CardFooter,
Input, Select, Switch, Checkbox, Label, Dialog, DataTable, Badge, Tabs...
```

**Claude plans**: "I'll use Card for each section, Switch for toggles, Select for dropdowns, Input for text fields. Layout will be a single-column stack following the form layout pattern from composition-patterns.md."

**Claude writes PreferencesPage.tsx** (first draft):

**Always-on PostToolUse hooks fire (3 in parallel):**
- `validate-tokens.py` → EXIT 2: "Line 15: hardcoded `#f9fafb` — use `bg-surface-secondary`"
- `check-imports.py` → EXIT 0 (Claude used design system components)
- `check-composition.py` → EXIT 2: "File uses `<Card>` but missing `<CardHeader>`. Card should contain CardHeader and CardContent."

**Claude fixes** — replaces the hex color with a token, adds CardHeader to each Card section.

**PostToolUse hooks fire again:**
- All three → EXIT 0. File passes.

**Claude continues** — adds notification settings section, privacy settings section, account details section. Each edit is validated and corrected as needed.

**Claude writes a new ToggleGroup component:**

**Skill-scoped PreToolUse agent handler fires** (component creation gatekeeper):
- Agent searches existing components
- Finds `<Switch>` in the component library
- Returns: `{"ok": false, "reason": "Existing component Switch at src/components/ui/switch.tsx provides toggle functionality. For grouped toggles, compose multiple Switch components in a form layout rather than creating a new ToggleGroup."}`

**Claude adjusts** — uses `<Switch>` components in a standard form layout instead of creating a new component.

**Claude finishes**: "I've built the preferences page with three sections..."

**Skill-scoped Stop hooks fire (2 in parallel):**

- **Agent handler** reads PreferencesPage.tsx, finds DashboardPage.tsx and ProfilePage.tsx for comparison.
  - Dashboard uses `grid-cols-2 gap-4` for cards
  - Profile uses `space-y-6` for stacked form sections
  - Preferences uses `space-y-6` — matches Profile's form pattern. Consistent.
  - Returns: `{"ok": true}`

- **Prompt handler** checks semantic HTML structure.
  - Headings follow h1 > h2 order, form elements have labels, sections use semantic grouping.
  - Returns: `{"ok": true}`

**Claude's response is delivered to the user.** The page uses existing components correctly, follows established layout patterns, uses design tokens throughout, and is semantically well-structured.

The user didn't check for any of this. The system did it automatically.

## Adapting This to Your Project

This worked example uses React + Tailwind + shadcn/ui. To adapt it:

1. **Update the component map** (`config/component-map.json`) with your actual design system components.

2. **Update the token rules** in `validate-tokens.py` to match your token system. If you use CSS custom properties, check for `var(--`. If you use Tailwind, the existing patterns mostly work. If you use CSS modules, adjust the regex patterns.

3. **Update the composition patterns** in `check-composition.py` to match your compound component APIs. Different component libraries use different composition patterns.

4. **Update the references** (`design-tokens.md` and `composition-patterns.md`) with your actual tokens and patterns. These are what Claude consults when fixing violations.

5. **Calibrate the strictness.** If your existing codebase has many violations, start with just the import checker and token validator. Add composition checking and the Stop hook audit once the baseline is clean. A validator that produces 50 violations per file will overwhelm Claude — start lean, tighten as the codebase improves.

The handlers and hooks are the infrastructure. The component map, token definitions, and pattern references are where your specific design system lives. Swap those out, and the same enforcement system works for any project.
