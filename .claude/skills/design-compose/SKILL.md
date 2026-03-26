---
name: design-compose
description: >
  Enforces design system consistency when building UI. Ensures existing
  components are used correctly through composition rather than creating
  new ones, and that design tokens are used instead of hardcoded values.
  Activates when building components, pages, layouts, or any front-end
  implementation work.
allowed-tools: Bash(python3 *), Read, Grep, Glob
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
          command: "python3 ${CLAUDE_SKILL_DIR}/scripts/validate-tokens.py"
        - type: command
          command: "python3 ${CLAUDE_SKILL_DIR}/scripts/check-imports.py"
  Stop:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-compose/scripts/log-hook.py --skill design-compose --event Stop"
        - type: prompt
          prompt: >
            Review the UI code written in this session. Check:
            (1) Are design system components used instead of raw HTML elements
            where available? (2) Are components composed following standard
            patterns — e.g., Card contains CardHeader + CardContent, Dialog
            contains DialogContent? (3) Are style overrides (className, style
            props) avoided on components that control their own appearance?
            If issues found, respond {"ok": false, "reason": "[specific
            issues and fixes]"}. If clean, respond {"ok": true}. $ARGUMENTS
---

# Design System Composer

You are building UI in a project with an established design system.
Your primary job is to **compose existing components**, not create new ones.

## Setup Check

Before starting, verify that design-setup has been run. Check if
`${CLAUDE_SKILL_DIR}/config/paths.json` exists.

If it does NOT exist, tell the user:

> "The design system hasn't been configured for this project yet.
> Run `/design-setup` first to discover your components and tokens."

Then stop. Do not proceed without configuration.

If it DOES exist, read `${CLAUDE_SKILL_DIR}/config/paths.json` to understand
the project structure, then read `${CLAUDE_SKILL_DIR}/config/component-map.json`
to understand available components.

## Core Rules

1. **Compose, don't create.** Use existing components for every UI element.
   Only create a new component if nothing in the component map serves the
   purpose, and explain why to the user first.

2. **Use the variant system.** Components have variants for a reason. Use
   `<Button variant="secondary">` not `<Button className="bg-gray-200">`.

3. **Tokens for everything.** All colors, spacing, typography, shadows, and
   border-radii come from design tokens. No hardcoded values. The PostToolUse
   hooks will catch violations automatically.

4. **Compound components stay compound.** Read `config/composition-rules.json`
   for required composition patterns. Don't skip the pieces.

5. **Match existing patterns.** Before building a page layout, read a similar
   existing page and match its structure.

## When Building a Page or View

1. Read the config files to understand available components
2. Look at 1-2 similar existing pages to understand composition patterns
3. Plan the layout using existing components
4. Build iteratively — the PostToolUse hooks will catch token and import
   violations on each edit and give you specific feedback
5. The Stop hook will do a final composition review when you're done

## When You Need Something New

If the component map doesn't have what you need:

1. Check if an existing component can serve the purpose with different props
2. Check if composing existing components together achieves the goal
3. Only if neither works, tell the user what you need and why, before creating it
