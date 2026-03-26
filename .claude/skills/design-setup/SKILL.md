---
name: design-setup
description: >
  Configure design system enforcement for a repository. Run once to discover
  reusable UI units (components), named visual values (tokens), and composition
  patterns. Generates config for the design-compose skill. Works across web
  frameworks, Flutter, SwiftUI, and any component-based UI system. Re-run if
  the repository structure changes.
disable-model-invocation: true
allowed-tools: Bash(python3 *), Read, Grep, Glob, AskUserQuestion
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "python3 ${CLAUDE_SKILL_DIR}/scripts/log-hook.py --skill design-setup --event UserPromptSubmit"
  PostToolUse:
    - hooks:
        - type: command
          command: "python3 ${CLAUDE_SKILL_DIR}/scripts/log-hook.py --skill design-setup --event PostToolUse"
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: >
            You are guiding an iterative design-system discovery process.
            A script just ran during design-setup. The output is in $ARGUMENTS.

            Evaluate the results on four dimensions:

            (1) COMPLETENESS — Did the script find what we're looking for?
            If it found component-like files in a directory, are there likely
            MORE in sibling directories or parent directories we haven't
            scanned yet? Look for clues like sibling_directories or
            subdirectories in the output.

            (2) CONFIDENCE — Are the results clearly what they claim to be,
            or ambiguous? A directory with 10 PascalCase files exporting
            named UI units is high confidence. A directory with 2 utility
            files is low confidence. For token files, 20+ named color/size
            values is high confidence; 3 assignments is low.

            (3) EXPANSION — Should we scan adjacent directories? If we found
            components in design/atoms/, we should also check design/molecules/
            and any other siblings listed in the output before concluding.

            (4) DEPTH — Should we go deeper into a subdirectory (it has many
            files), or zoom out to the parent (current dir seems too narrow)?

            Respond {"ok": true} if the results are sufficient for the current
            discovery phase and can be presented to the user for confirmation.

            Respond {"ok": false, "reason": "SPECIFIC_NEXT_ACTION"} if more
            scanning is needed. Be specific: "Scan sibling directory 'molecules'
            at path X" or "Results are empty — ask the user directly where
            their components live" or "Found tokens but no spacing values —
            scan for additional token files."
  Stop:
    - hooks:
        - type: command
          command: "python3 ${CLAUDE_SKILL_DIR}/scripts/log-hook.py --skill design-setup --event Stop"
        - type: prompt
          prompt: >
            Check if the design-setup process is complete. The process has
            these phases: (1) ecosystem confirmed, (2) component directories
            identified and components cataloged, (3) token files found and
            values extracted, (4) composition examples identified, and
            (5) config generated for design-compose. Review the conversation.
            If any phase was skipped or produced no results without the user
            being informed, respond {"ok": false, "reason": "Phase [X] not
            completed. [What needs to happen]"}. If all phases are done and
            config was generated, respond {"ok": true}. $ARGUMENTS
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
   results are sufficient, present findings to the user:

   > "I found your UI components in `src/lib/design/`:
   > - **atoms/**: Btn, TextInput (2 components)
   > - **molecules/**: CardBlock (1 component)
   > - Barrel export in index.ts re-exports all 3
   >
   > Is this your design system's component directory?"

5. After confirmation, read the actual component files to understand their APIs.
   For each component, build a record:
   - `name`: Component name
   - `file`: File path
   - `import_path`: How to import it
   - `replaces`: What raw element/widget it replaces (if applicable)
   - `variants`: Available variants
   - `expected_children`: For compound components
   - `style_controlled`: Whether style overrides should be blocked

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

3. The PostToolUse hook evaluates: enough tokens? All categories covered?
   It may say "also check this file" or "no tokens found, ask the user."

4. Present findings with categories and spacing base:

   > "I found design tokens in two files:
   > - `_variables.scss`: 11 colors, 7 spacing values (6px base grid), 8 typography
   > - `tokens.ts`: mirrors the SCSS values in TypeScript
   >
   > Your spacing uses a **6px base grid**. Is that correct?"

5. Ask: "Any other files where visual values are defined?"

## Phase 4: Discover Composition Examples

1. From confirmed component names, find where they're used:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/find-importers.py --root . --names '["Btn","CardBlock","TextInput"]'
   ```

2. Present the top composition files:

   > "Your components are composed in these files:
   > - `src/routes/dashboard/+page.svelte` uses Btn, CardBlock
   > - `src/routes/settings/+page.svelte` uses Btn, TextInput, CardBlock
   >
   > Which of these best represents your design patterns?"

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

> "Setup complete. I've configured `design-compose` with:
> - **3 components** mapped (Btn, TextInput, CardBlock)
> - **Token enforcement** for colors, spacing (6px grid), typography
> - **Composition examples** from your dashboard and settings pages
>
> Use `/design-compose` when building UI. Run `/design-setup` again if
> the repository structure changes."

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
