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
            A script just ran. The output is in $ARGUMENTS.

            Identify which script ran from the command, then evaluate:

            **scan-dir-deep.py** (component directory scan):
            - If exported names were found, check sibling_directories and
              subdirectories — if there are unscanned dirs with files, say
              {"ok": false, "reason": "Also scan sibling dir X"}.
            - If exports were found and no siblings remain, the NEXT step is
              to check import frequency. Say {"ok": false, "reason": "Found
              [N] exports. Now run find-importers.py with these names to
              check which ones are actively reused vs one-offs."}.
            - If nothing was found, say {"ok": false, "reason": "No exports
              found. Try scanning subdirectories or ask the user."}.

            **find-importers.py** (import frequency check):
            - Look at the import counts. Components with 10+ imports are
              likely core design system components. Under 5 are likely one-offs.
            - Say {"ok": true} — the results now have frequency data and are
              ready to present to the user. Suggest filtering to 10+ imports.

            **find-value-files.py** (token file finder):
            - If candidates with scores 60+ were found, say {"ok": true}.
            - If only low-score candidates or 0 found, say {"ok": false,
              "reason": "Ask the user where design tokens are defined."}.

            **extract-named-values.py** (token file analysis):
            - If 10+ named values found across multiple categories, say
              {"ok": true} — this is sufficient even from a single file.
            - If fewer than 5 values, say {"ok": false, "reason": "Very
              few tokens. Check for additional token files."}.

            **Any other Bash command** (grep, echo, etc.):
            - Say {"ok": true} — don't interfere with general commands.
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

## Phase 1: Interpret Ecosystem and Confirm

The auto-detected results above are RAW SIGNALS, not a conclusion. You need to
interpret them. Look at:
- `ecosystem_candidates` — config files found and what they suggest
- `frameworks_from_deps` — what package.json dependencies indicate
- `file_extension_counts` — which language actually dominates the repo
- `libraries`, `styling_systems` — what UI tools are in use

Use your judgment to synthesize these into a clear picture. For example, if the
signals show Rust from Cargo.toml BUT also React from deps, TypeScript is true,
and .ts files dominate the extension counts — this is a TypeScript/React project
with Rust build tooling, not a Rust project.

Present your interpretation to the user:

> "Based on the signals, this looks like a **TypeScript/React** monorepo using
> **Tailwind CSS** and **Emotion** for styling, with **Radix UI** and **Material UI**
> component libraries. I also see Cargo.toml which appears to be build tooling
> rather than the primary ecosystem. Does that sound right?"

If the user corrects something, update your understanding before proceeding.

## Phase 2: Discover Reusable UI Units (Components)

This phase is **iterative** and uses a combination of tools. The goal is not just
to find components, but to identify which ones are **core design system components
meant for reuse** vs. one-off components that happen to be exported.

The key signal is **import frequency** — a component imported by 100+ files is
clearly a shared primitive. One imported by 2 files is a one-off.

### Step 2a: Find candidate directories

Use Grep and Glob (your built-in tools) to search for component-like patterns.
Look at the structure scan's `notable_dirs` for promising names (components, ui,
atoms, widgets, design, lib, shared, kit, etc.)

For the most promising candidates, use `scan-dir-deep.py` to get a structured
view of exports:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/scan-dir-deep.py --dir <path>
```

The PostToolUse hook evaluates and may guide you to scan siblings, go deeper,
or move on.

### Step 2b: Check import frequency

Once you have a list of exported component names, check which ones are actually
reused across the codebase:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/find-importers.py --root . --names '["Button","Card","RedoButton","RedoModal"]'
```

The PostToolUse hook will see the import counts and help you filter:
- **High frequency (20+ imports)**: Core design system component. Include it.
- **Medium frequency (5-19 imports)**: Likely shared. Include it.
- **Low frequency (1-4 imports)**: Probably a one-off. Ask the user or skip.

This is how you distinguish design system components from one-offs. A repo might
have 200 exported components, but only 20-30 are the shared primitives that
design-compose should enforce.

### Step 2c: Handle multiple component systems

Some projects have layered component systems (e.g., shadcn/ui primitives AND
a custom component library built on top of them). If you find components in
multiple directories, present BOTH to the user and ask which layer(s) should
be enforced:

> "I found two component systems:
> 1. **shadcn/ui** in `components/ui/` — 29 low-level primitives (Button, Card, Dialog...)
> 2. **Arbiter components** in `arbiter-components/` — 47 higher-level components (RedoButton, RedoModal, RedoTable...)
>
> RedoButton is imported 193 times, shadcn Button 271 times — both are heavily used.
>
> Should I enforce both layers, or focus on one?"

### Step 2d: Present and confirm

Present findings as a **formatted table** sorted by import frequency:

> ### Core Design System Components
>
> | Component | Location | Imports | Type | Notes |
> |-----------|----------|---------|------|-------|
> | `Button` | `components/ui/button.tsx` | 271 | Primitive | shadcn/ui, 5 variants |
> | `RedoButton` | `arbiter-components/buttons/redo-button.tsx` | 193 | Primitive | Custom, themed |
> | `RedoTextInput` | `arbiter-components/input/redo-text-input.tsx` | 120 | Primitive | Custom input |
> | `Card` | `components/ui/card.tsx` | 31 | Compound | CardHeader + CardContent |
> | ... | | | | |
>
> **Showing components with 10+ imports. Is this your design system?**

### Step 2e: Catalog confirmed components

After confirmation, read the actual component files to understand their APIs.
Build a record for **every** confirmed component:
- `name`: Component name (e.g., "RedoButton")
- `file`: File path
- `import_path`: How to import it
- `replaces`: The raw HTML element this replaces, in element form:
  - Button → `<button`, Input → `<input`, Dialog → `<dialog`, Link → `<a `
  - For compound containers like Card that wrap `<div>`, leave empty
- `variants`: Available variants
- `expected_children`: For compound components
- `style_controlled`: true if className/style overrides should be blocked
- `import_frequency`: How many files import this component

Ask: "Are there other component directories I should check?"

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
