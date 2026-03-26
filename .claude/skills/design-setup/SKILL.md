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
            - Look at structural signals in the output:
              * barrel_export with PascalCase names = high confidence design system
              * consistent naming_pattern = intentional organization
              * subdirectories like atoms/molecules = atomic design structure
            - If the structural signals are strong (barrel exports, dedicated
              directory, consistent naming), these are likely design system
              components even without import data. Say {"ok": true} and note
              the confidence signals.
            - If structural signals are weak (random directory, mixed naming,
              no barrel), suggest checking import frequency: {"ok": false,
              "reason": "Structural signals are ambiguous. Run find-importers
              to check which components are actively reused."}.
            - If nothing was found, say {"ok": false, "reason": "No exports
              found. Try scanning subdirectories or ask the user."}.

            **find-importers.py** (import frequency check):
            - Look at the import counts to RANK and CONFIRM. High counts
              confirm design system components. But low counts don't
              disqualify — components in a dedicated design system directory
              might just be new.
            - Say {"ok": true} — the data is ready to present.

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

This phase is **iterative** and uses multiple signals to identify which components
are **core design system components meant for reuse**. No single signal is
definitive — use your judgment to weigh them together.

### Signals that indicate a design system component

**Structural signals** (work even in brand-new repos with zero usage):
- **Dedicated directory**: Files in `components/ui/`, `design-system/`, `atoms/`,
  `primitives/` are placed there intentionally. One-offs don't get organized.
- **Barrel exports**: An `index.ts` re-exporting 15 components is a deliberate
  public API. One-offs don't get barrel files.
- **Consistent naming**: All PascalCase, all prefixed (`Redo*`), all following
  a pattern (`*.component.ts`) — intentional organization.
- **Co-located styles**: `button.module.css` next to `button.tsx` — a component
  that owns its styling.
- **Component API patterns**: Props interfaces, variant systems, `children` props,
  `forwardRef` — written to be reused. One-offs don't bother with variant systems.
- **Storybook stories**: `.stories.tsx` files mean someone invested in documenting
  the component for reuse.

**Usage signals** (available in repos with existing code):
- **Import frequency**: A component imported by 100+ files is obviously shared.
  Under 5 imports might be a one-off — or might be new. Frequency confirms
  but absence doesn't disqualify.

Use **structural signals first** to identify candidates, then **import frequency
to confirm and rank** when usage data exists. In a new project with no imports,
structural signals alone are sufficient.

### Step 2a: Find candidate directories

Use Grep and Glob (your built-in tools) to search for component-like patterns.
Look at the structure scan's `notable_dirs` for promising names (components, ui,
atoms, widgets, design, lib, shared, kit, etc.)

For promising candidates, use `scan-dir-deep.py` to get a structured view:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/scan-dir-deep.py --dir <path>
```

The PostToolUse hook evaluates and may guide you to scan siblings, go deeper,
or move to the next step.

### Step 2b: Assess confidence using available signals

Look at what `scan-dir-deep` returned and apply your judgment:

- **Barrel export re-exporting PascalCase names?** → High confidence these are
  the design system's public API.
- **Consistent naming pattern across files?** → Intentional organization.
- **Subdirectories like atoms/molecules/organisms?** → Atomic design structure,
  clearly a design system.
- **Few files but well-structured with props/variants?** → Quality over quantity.

If the repo has existing code, check import frequency to confirm:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/find-importers.py --root . --names '["Button","Card","Input"]'
```

Import frequency helps **rank** components in mature repos, but don't exclude
components from a dedicated design system directory just because they have low
import counts — they might be newly added.

### Step 2c: Handle multiple component systems

Some projects have layered component systems. If you find components in
multiple directories, present BOTH and ask:

> "I found two component layers:
> 1. **shadcn/ui** in `components/ui/` — 29 low-level primitives
> 2. **Arbiter components** in `arbiter-components/` — 47 higher-level components
>
> Should I enforce both layers, or focus on one?"

### Step 2d: Present initial findings

Present what you found as a **formatted table**, then explicitly acknowledge
that **you probably missed things** and ask the user to fill in the gaps.

> ### Design System Components (auto-discovered)
>
> | Component | Location | Imports | Type |
> |-----------|----------|---------|------|
> | `Button` | `components/ui/button.tsx` | 271 | Primitive |
> | `RedoButton` | `arbiter-components/buttons/` | 193 | Primitive |
> | `Card` | `components/ui/card.tsx` | 31 | Compound |
> | ... | | | |
>
> I found these by scanning component directories and checking import frequency.
> **But I may have missed components that live outside these directories —
> for example, layout primitives or wrappers that sit at the source root.**
>
> What core components am I missing?

**This question is critical.** In large repos, important components often live
in unexpected places (e.g., `Flex` and `Text` at the source root, not in a
components directory). The user knows their design system better than any
script can discover it.

### Step 2e: Iterate with the user (LOOP)

When the user tells you about missing components:

1. **Search for them**: Use Grep to find where they're defined:
   ```
   Grep for "export.*function Flex" or "export.*const Flex" in .tsx/.ts files
   ```

2. **Check their import frequency** to confirm importance:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/find-importers.py --root . --names '["Flex","Text"]'
   ```

3. **Add them to the table** and present the updated catalog:

   > Added to catalog:
   >
   > | Component | Location | Imports | Type |
   > |-----------|----------|---------|------|
   > | `Flex` | `src/flex.tsx` | 514 | Layout |
   > | `Text` | `src/text.tsx` | 504 | Typography |
   >
   > These are actually your most-used components! Anything else I'm missing?

4. **Repeat** until the user says the catalog is complete.

This loop is expected to run 2-3 times. The scripts get the obvious stuff,
the user fills in the rest. Don't rush through this — a complete component
catalog is the foundation everything else builds on.

### Step 2f: Catalog confirmed components

After the user confirms the catalog is complete, read the actual component
files to understand their APIs. Build a record for **every** confirmed component:
- `name`: Component name
- `file`: File path
- `import_path`: How to import it
- `replaces`: The raw HTML element this replaces (`<button`, `<input`, etc.)
  Leave empty for compound containers like Card.
- `variants`: Available variants
- `expected_children`: For compound components
- `style_controlled`: true if style overrides should be blocked

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
