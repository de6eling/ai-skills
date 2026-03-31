---
name: design-compose
description: >
  Enforces design system consistency when building UI. Ensures existing
  components are used correctly through composition rather than creating
  new ones, and that design tokens are used instead of hardcoded values.
  Activates when building components, pages, layouts, or any front-end
  implementation work.
allowed-tools: Bash(python3 *), Read, Write, Edit, Grep, Glob
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/log-hook.py --skill design-compose --event UserPromptSubmit"
  PostToolUse:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/log-hook.py --skill design-compose --event PostToolUse"
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/validate-tokens.py"
          statusMessage: "Checking design tokens..."
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/check-imports.py"
          statusMessage: "Checking component imports..."
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/check-new-components.py"
          statusMessage: "Checking for new components..."
  Stop:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/log-hook.py --skill design-compose --event Stop"
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/validate-stop.py"
          statusMessage: "Running final design system validation..."
---

# Design System Composer

Compose existing components — don't create new ones.

## Before You Start

Look for `config/paths.json` inside the skill's directory
(`.claude/skills/design-compose/config/paths.json`). If not found,
tell the user to run `/design-setup` first and stop.

If it exists, read `paths.json`, `component-map.json`, and
`composition-rules.json` from that config directory to understand the
project's components, tokens, and compound patterns.

Note: `$CLAUDE_PROJECT_DIR` is the only path variable available in
hook commands. It points to the project root. There is no
`$CLAUDE_SKILL_DIR` variable — that was a common gotcha we discovered.
Hook commands must use the full path:
`$CLAUDE_PROJECT_DIR/.claude/skills/design-compose/...`

## Rules

1. **Compose, don't create.** Only create new components if nothing in
   the catalog works, and explain why to the user first.
2. **Use variants and props.** Not className overrides.
3. **Tokens for everything.** No hardcoded colors, sizes, or spacing.
4. **Compound components stay compound.** Follow composition-rules.json.
5. **Match existing patterns.** Read a similar page before building.

## Workflow

1. Read configs and 1–2 similar existing pages
2. Build using existing components
3. After each Write/Edit, report the validation results (see below)
4. If a hook flags new undocumented components, ask the user about each
5. If a hook flags a violation, fix it before continuing

## Reporting Validation Results

Three Python scripts run automatically after every Write/Edit. After
each file write, show what they found:

```
Scripts ran (PostToolUse → Edit|Write):
  ✓ validate-tokens.py — no hardcoded values
  ✓ check-imports.py — design system components used correctly
  ✓ check-new-components.py — all components in catalog
Full log: .claude/logs/validation.log
```

Show ✗ for failures and fix them. At the end, report the Stop hook's
final scan of all modified files. Point the designer to
`.claude/logs/validation.log` for the full record — the scripts
document themselves there with timestamps and results.
