---
name: design-setup
description: >
  Configure design system enforcement for a repository. Run once in a new
  project to discover components, tokens, and patterns, then generate config
  for the design-compose skill. Use when setting up a new project for design
  work, or when the repository structure has changed and enforcement needs
  to be reconfigured.
disable-model-invocation: true
allowed-tools: Bash(python *), Read, Grep, Glob, AskUserQuestion
hooks:
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: >
            A discovery script just ran during design-setup. Examine the
            script output in $ARGUMENTS. Evaluate:
            (1) Did the script find meaningful results, or did it come back
            mostly empty?
            (2) If results were found, do they look reasonable for the type
            of repository being analyzed?
            (3) If results are sparse or low-confidence, should the user be
            asked to provide the information manually?
            Respond {"ok": true} if the results look useful enough to
            present to the user. Respond {"ok": false, "reason": "The scan
            found [little/nothing]. Ask the user directly: [specific
            question to ask]"} if the results are insufficient.
  Stop:
    - hooks:
        - type: prompt
          prompt: >
            Check if the design-setup process is complete. The setup has
            multiple phases: (1) framework detection, (2) component discovery,
            (3) token discovery, (4) page/pattern discovery, and (5) config
            generation. Review the conversation so far. If any phase was
            skipped or produced no results without the user being asked about
            it, respond {"ok": false, "reason": "Phase [X] was not completed.
            [Describe what still needs to happen]"}. If all phases are complete
            and config has been generated, respond {"ok": true}. $ARGUMENTS
---

# Design System Setup

You are running the design-setup wizard. Your job is to explore this repository,
understand its design system, and generate configuration files that the
`design-compose` skill will use to enforce consistency.

**Important**: Ask the user ONE question at a time. Wait for their answer before
proceeding. Never ask multiple questions in one message.

## Framework Context (auto-detected)

The framework detector ran automatically when this skill was invoked.
Here are the results:

!`python3 ${CLAUDE_SKILL_DIR}/scripts/detect-framework.py`

Use this context throughout the setup process. Pass it to subsequent scripts
as their `--context` argument.

## Phase 1: Confirm Framework Detection

Present the auto-detected framework results to the user in plain language.
For example:

> "This looks like a **Next.js** project using **TypeScript** and **Tailwind CSS**,
> with **shadcn/ui** components. Does that sound right?"

If the detection confidence is "low" or the user corrects something, adjust
your understanding before proceeding. If the user corrects the framework,
update the context JSON you'll pass to subsequent scripts.

## Phase 2: Component Discovery

Run the component finder with the framework context:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/find-components.py --context '<framework_json>'
```

The PostToolUse prompt hook will evaluate whether the scan found useful results.
If the hook says results are insufficient, ask the user directly instead of
presenting empty results.

For the top candidates, ask the user to confirm:

> "I found what looks like your main component library at `src/components/ui/`
> with 14 component files including Button, Card, Input, and Dialog.
> Is this your design system's component directory?"

If the user confirms, read a few of the actual component files to understand:
- What props/variants each component supports
- Which raw HTML element each component replaces
- Whether components are compound (Card + CardHeader + CardContent)
- Whether components control their own styling (no className override expected)

For each confirmed component, build a record with:
- `name`: Component name (e.g., "Button")
- `file`: File path
- `import_path`: How to import it (e.g., "@/components/ui/button")
- `replaces_element`: Raw HTML it replaces (e.g., "<button")
- `variants`: Available variants (e.g., ["default", "secondary", "outline"])
- `expected_children`: For compound components (e.g., ["CardHeader", "CardContent"])
- `style_controlled`: Whether className overrides should be blocked

Ask the user:

> "I found these [N] components. Are there any other component directories
> I should know about, or any components I missed?"

## Phase 3: Token Discovery

Run the token finder:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/find-tokens.py --context '<framework_json>'
```

Again, the PostToolUse hook evaluates the scan quality. Present findings:

> "I found design tokens in these locations:
> - `src/app/globals.css` — 45 CSS custom properties (23 colors, 8 spacing, 6 typography)
> - `tailwind.config.ts` — custom colors using CSS variables, custom spacing
>
> Is this where your design tokens are defined? Are there other sources I should check?"

Read the actual token files to extract:
- Color token names and their values
- Spacing scale (and the base unit — 4px? 8px?)
- Typography tokens (font sizes, weights, line heights)
- Shadow tokens
- Border radius tokens

Ask the user:

> "Your spacing appears to use a [N]px base grid. Is that correct?"

## Phase 4: Page and Pattern Discovery

Run the page finder:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/find-pages.py --context '<framework_json>'
```

This finds where components are actually composed into pages/views. Present:

> "I found [N] pages/views. The most commonly used components across your
> pages are: Button (used in 12 pages), Card (8 pages), Input (7 pages).
>
> Which pages would you consider the best examples of your design patterns?
> These will be used as references for composition consistency."

Read the user's suggested reference pages to understand current composition
patterns (layout structure, component arrangement, spacing between sections).

## Phase 5: Generate Configuration

Once all phases are confirmed, collect all the information into a single JSON
object and pass it to the config generator:

```bash
echo '<collected_config_json>' | python3 ${CLAUDE_SKILL_DIR}/scripts/generate-config.py
```

The config JSON should include:
- `framework`: framework ID from Phase 1
- `framework_name`: human-readable name
- `component_extensions`: file extensions for UI files
- `component_directory`: primary component directory
- `component_directories_all`: all component directories
- `confirmed_components`: array of component records from Phase 2
- `confirmed_token_sources`: array of token sources from Phase 3
- `token_system`: "tailwind", "css-variables", "scss", etc.
- `spacing_base`: base spacing unit in pixels
- `page_directories`: directories containing pages/views
- `skip_directories`: directories to ignore during validation

Tell the user what was generated:

> "Setup complete. I've generated configuration for the `design-compose` skill:
> - **Component map**: [N] components mapped (Button, Card, Input, ...)
> - **Token patterns**: [N] forbidden patterns, [spacing_base]px grid
> - **Path config**: Components at `[path]`, pages at `[path]`
> - **Composition rules**: [N] compound component patterns
>
> You can now use `/design-compose` when building UI, and the always-on
> hooks will enforce token and component usage on every edit.
>
> If your repository structure changes, run `/design-setup` again to
> reconfigure."

## Error Handling

If any script produces no results or low-confidence results, the PostToolUse
prompt hook will flag this. When that happens:
- Don't skip the phase. Ask the user directly.
- For components: "I couldn't automatically detect your component directory. Where do your UI components live?"
- For tokens: "I didn't find a clear token system. How do you define your colors and spacing? (CSS variables, Tailwind config, SCSS variables, etc.)"
- For pages: "I couldn't find a standard pages directory. Where are your main views/routes?"

The user always has the final say. Scripts provide suggestions; the user confirms.
