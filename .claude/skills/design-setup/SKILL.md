---
name: design-setup
description: >
  Configure design system enforcement for a repository. Run once to discover
  reusable UI units (components), named visual values (tokens), and composition
  patterns. Generates config for the design-compose skill. Works across web
  frameworks, Flutter, SwiftUI, and any component-based UI system. Re-run if
  the repository structure changes.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-setup/scripts/log-hook.py --skill design-setup --event UserPromptSubmit"
  PostToolUse:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-setup/scripts/log-hook.py --skill design-setup --event PostToolUse"
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: >
            You are guiding an iterative design-system discovery process.
            A script just ran during design-setup. The output is in $ARGUMENTS.

            Evaluate whether the results are SUFFICIENT to present to the user,
            or whether more scanning is needed. Use these criteria:

            SUFFICIENT (respond {"ok": true}) when:
            - A component directory scan found exported names and the directory
              has no unscanned subdirectories with significant file counts
            - A token/value file scan found candidates with scores above 30
            - A single file analysis found 10+ named values across multiple
              categories (colors, sizes, fonts, etc.) — this IS comprehensive
              even if it is only one file. Many projects define all tokens in
              one file and that is normal.
            - An importer search found files that use multiple components

            INSUFFICIENT (respond {"ok": false, "reason": "..."}) when:
            - A component scan found exported names BUT sibling_directories
              or subdirectories in the output contain unscanned dirs with
              files — scan those before concluding
            - A token scan found 0 candidates — ask the user directly
            - A file analysis found fewer than 5 named values — look for
              additional files
            - Results are completely empty — ask the user

            IMPORTANT: Do NOT reject results just because there is only one
            file. A single globals.css with 100+ tokens or a single theme.ts
            with 30 values is a COMPLETE token source. Quality and quantity
            of values matters more than number of files.

            When responding {"ok": false}, be specific about what to do next:
            "Scan sibling directory X" or "Ask the user where tokens are defined."
  Stop:
    - hooks:
        - type: command
          command: "python3 $CLAUDE_PROJECT_DIR/.claude/skills/design-setup/scripts/log-hook.py --skill design-setup --event Stop"
        - type: prompt
          prompt: >
            Check if the design-setup process is complete. It has these phases:
            (1) ecosystem confirmed (2) components discovered (3) tokens found
            (4) composition examples identified (5) config generated.

            Respond {"ok": true} if the user has been presented results for
            each phase and either confirmed or the phase was addressed.
            Phases where the user said "looks good", "yes", "that's right",
            or similar count as confirmed. If Claude is currently waiting for
            a user answer, that also counts as the phase being in progress
            and is OK.

            Respond {"ok": false, "reason": "..."} ONLY if a phase was
            completely skipped with no user interaction at all. $ARGUMENTS
---

# Design System Setup

You are running the design-setup wizard. Your job is to explore this repository,
discover its design system, and generate configuration for `design-compose`.

**Important**: Ask the user ONE question at a time. Wait for their answer before
proceeding. Never ask multiple questions in one message.

## Auto-Detected: Repository Structure

!`python3 ${CLAUDE_SKILL_DIR}/scripts/scan-structure.py`

## Auto-Detected: Project Ecosystem

!`python3 ${CLAUDE_SKILL_DIR}/scripts/identify-ecosystem.py`

Use these results throughout the setup process.

---

## Phase 1: Confirm Ecosystem

Present the auto-detected ecosystem to the user in plain language. For example:

> "This looks like a **SvelteKit** project using **TypeScript** with **Sass/SCSS**
> styling. I also detected the **PrimeNG** component library. Does that sound right?"

If the user corrects something, update your understanding before proceeding.

## Phase 2: Discover Reusable UI Units (Components)

This phase is **iterative**. Start broad, then narrow based on the PostToolUse
prompt handler's guidance.

1. Look at the structure scan's `notable_dirs` for directories with names suggesting
   reusable units (components, ui, atoms, widgets, design, lib, shared, kit, etc.)

2. For the most promising candidate, run a deep scan:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan-dir-deep.py --dir <path>
   ```

3. The PostToolUse hook will evaluate and may tell you to:
   - **Scan siblings**: "Also scan design/molecules/ next to design/atoms/"
   - **Go deeper**: "This directory has subdirectories with more files, scan those"
   - **Ask the user**: "Results are ambiguous, ask the user to confirm"
   - **Move on**: "This looks complete, present to the user"

4. Follow the hook's guidance. Run more scans as directed. When the hook says
   results are sufficient, present findings to the user **as a formatted table**:

   > ### Components Found in `src/components/ui/`
   >
   > | File | Components | Type | Notes |
   > |------|-----------|------|-------|
   > | `button.tsx` | `Button` | Primitive | Variants: default, secondary, outline, ghost, destructive |
   > | `card.tsx` | `Card`, `CardHeader`, `CardContent`, `CardFooter` | Compound | Requires CardHeader + CardContent children |
   > | `dialog.tsx` | `Dialog`, `DialogTrigger`, `DialogContent`, ... | Compound | 10 sub-components |
   > | `input.tsx` | `Input` | Primitive | |
   >
   > **4 files, 19 total exports, barrel export: none**
   >
   > Is this your complete set of UI components, or are there other directories I should check?

   Always use a table for component presentation. Include file name, exported
   component names, whether it's a primitive or compound component, and any
   notable details (variants, required children, etc.)

5. After confirmation, read the actual component files to understand their APIs.
   Build a record for **every** component (not just primitives). Include:
   - `name`: Component name (e.g., "Button")
   - `file`: File path (e.g., "src/components/ui/button.tsx")
   - `import_path`: How to import it (e.g., "@/components/ui/button")
   - `replaces`: The raw HTML element this replaces, in element form:
     - Button → `<button`
     - Input → `<input`
     - Dialog → `<dialog`
     - Link → `<a `
     - For compound containers like Card that wrap `<div>`, leave empty
   - `variants`: Available variants (e.g., ["default", "secondary", "outline"])
   - `expected_children`: For compound components (e.g., ["CardHeader", "CardContent"])
   - `style_controlled`: true if className/style overrides should be blocked

   **Important**: Include ALL components in the record, even compound ones
   without a direct `replaces` element. They still need composition rules.

6. Ask: "Are there other directories with reusable UI units I should know about?"

## Phase 3: Discover Named Visual Values (Tokens)

Also **iterative**.

1. Run the value file finder:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/find-value-files.py --root .
   ```

2. For top candidates, analyze each one:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/extract-named-values.py --file <path>
   ```

3. The PostToolUse hook evaluates whether enough tokens were found. A single
   file with 20+ values across multiple categories is sufficient — many projects
   define all tokens in one file.

4. Present findings **as a formatted table** with categories and spacing base:

   > ### Design Tokens Found
   >
   > | Source | Format | Colors | Spacing | Typography | Shadows | Radius | Total |
   > |--------|--------|--------|---------|------------|---------|--------|-------|
   > | `src/app/globals.css` | CSS custom properties | 62 | — | 3 | — | 8 | 104 |
   >
   > **Spacing base**: not detected (no raw pixel spacing values — uses Tailwind utilities)
   >
   > Does this capture your design token system?

5. Ask: "Any other files where visual values are defined?"

## Phase 4: Discover Composition Examples

1. From confirmed component names, find where they're used:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/find-importers.py --root . --names '["Button","Card","Input"]'
   ```

2. Present the top composition files:

   > ### Composition Map
   >
   > | Page | Components Used |
   > |------|----------------|
   > | `src/app/settings/page.tsx` | Button, Card, CardHeader, CardContent, CardFooter, Input |
   > | `src/app/page.tsx` | Image |
   >
   > Which of these best represents your design patterns?

## Phase 5: Generate Configuration

Collect all confirmed information into a JSON object and generate config:

```bash
echo '<collected_config_json>' | python3 ${CLAUDE_SKILL_DIR}/scripts/generate-config.py
```

The config JSON should include:
- `ecosystem`, `language`: from Phase 1
- `ui_file_extensions`: from ecosystem detection
- `component_directory`, `component_directories_all`: from Phase 2
- `confirmed_components`: array of component records from Phase 2
- `confirmed_token_sources`: array of token source records from Phase 3 (each with path and categories list)
- `spacing_base_px`: from Phase 3 token analysis
- `composition_examples`: from Phase 4
- `skip_directories`: standard list for this ecosystem

Report what was generated:

> ### Setup Complete
>
> | Config | Details |
> |--------|---------|
> | Components | 4 mapped (Button, Card, Dialog, Input) |
> | Token enforcement | Colors, typography, radius from `globals.css` |
> | Composition examples | `settings/page.tsx` |
>
> Use `/design-compose` when building UI. Run `/design-setup` again if
> the repository structure changes.

## Error Handling

When scripts return sparse or empty results, the PostToolUse hook will flag it.
When that happens, ask the user directly:

- Components: "I couldn't automatically detect your UI components. Where do your reusable UI units live?"
- Tokens: "I didn't find a clear token/value system. How do you define your colors and spacing?"
- Composition: "I couldn't find files that use your components. Where are your main views or pages?"

If the project uses an external theming system (PrimeNG, Material, etc.) with
no local tokens, acknowledge that:

> "It looks like your visual values come from PrimeNG's built-in theme system
> rather than project-level tokens. Should I configure enforcement to use
> PrimeNG's CSS variables (--p-primary-color, etc.), or do you have custom
> overrides?"

The user always has the final say. Scripts provide suggestions; the user confirms.
