# Part 3: Where Handlers Run

A handler's *type* determines what it does (script, prompt, agent, HTTP). Where you *put* it determines when it's active and who it affects. Getting the placement wrong means either too much enforcement (slowing down every task with design checks when someone's writing a backend script) or too little (design rules that only apply when someone remembers to invoke a skill).

## The Three Scopes

### Always-On: Settings-Level Hooks

Hooks defined in `.claude/settings.json` (project) or `~/.claude/settings.json` (user) run in **every session, on every matching event, regardless of what Claude is doing.**

```json
// .claude/settings.json (committed to the repo — everyone gets these)
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/validate-tokens.py"
          }
        ]
      }
    ]
  }
}
```

**Use settings-level hooks for rules that should never be broken, regardless of context.**

Good candidates for always-on:
- Design token validation (no hardcoded colors, ever)
- Protected file blocking (don't edit the design system source without explicit intent)
- Import enforcement (always use the design system components)
- Accessibility baselines (every image needs alt text, every interactive element needs ARIA)

Bad candidates for always-on:
- Full composition audits (too slow to run on every edit)
- Layout coherence checks (irrelevant when editing non-UI files)
- Figma comparison (only relevant during design-to-code work)

The risk of always-on hooks is noise. If a developer is editing a Node.js API route and the token validator fires on every edit looking for CSS colors, it wastes time even though it exits immediately. Well-written validators handle this gracefully — check the file extension first, exit 0 instantly for non-UI files — but it's worth considering whether a rule genuinely applies to every file in the project.

#### Project vs. User vs. Local Settings

| File | Who it affects | Committed to repo? |
|---|---|---|
| `.claude/settings.json` | Everyone who clones the project | Yes — this is how you share design rules with the team |
| `.claude/settings.local.json` | Only you, in this project | No — gitignored. Good for personal preference hooks |
| `~/.claude/settings.json` | You, across all projects | No — lives on your machine. Good for cross-project habits |
| Managed policy settings | Everyone in the organization | Admin-controlled. Good for org-wide design standards |

For design system enforcement, **project settings** (`.claude/settings.json`) are almost always right. The rules travel with the codebase. When a new team member clones the repo, they get the validators automatically.

### Contextual: Skill-Scoped Hooks

Hooks defined in a skill's YAML frontmatter run **only while that skill is active**. When the skill activates (either because Claude loaded it automatically or the user invoked it with `/skill-name`), the hooks register in memory. When the skill finishes, they're cleaned up.

```yaml
---
name: design-to-code
description: Convert Figma designs to code with design system enforcement
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "python $CLAUDE_PROJECT_DIR/.claude/skills/design-to-code/scripts/validate-composition.py"
  Stop:
    - hooks:
        - type: agent
          prompt: >
            Review all files modified in this session. For each UI component:
            (1) Check that it uses design system components, not raw HTML.
            (2) Verify that component props match the design spec.
            (3) Check spacing and layout against established patterns.
            Report any violations. $ARGUMENTS
          timeout: 120
---

When converting a Figma design to code:
1. Pull the design context using get_design_context
2. Map Figma components to existing design system components
3. Implement the layout using composition, not new components
...
```

**Use skill-scoped hooks for enforcement that only makes sense during specific workflows.**

Good candidates for skill-scoped:
- Composition audits (expensive, only valuable during UI building)
- Figma comparison checks (only relevant when working from a design)
- Layout pattern matching (only valuable when building pages/views)
- Component creation gatekeeping (only when the skill is about building UI)

**Important:** `$CLAUDE_PROJECT_DIR` is the only path variable available in hook commands — it points to the project root. There is no `$CLAUDE_SKILL_DIR` variable for shell commands (this is a common gotcha). Hook commands must use the full path: `$CLAUDE_PROJECT_DIR/.claude/skills/<skill-name>/scripts/...`. Note that `${CLAUDE_SKILL_DIR}` *does* work inside SKILL.md body text where Claude interprets it, but not in the shell commands that hooks execute.

#### When Skills Activate

A skill's hooks start running when the skill is loaded. This happens in two ways:

1. **User invocation**: Someone types `/design-to-code`. The skill activates immediately, hooks register, and they stay active until the skill finishes its work.

2. **Automatic activation**: Claude reads the skill's `description` and decides it's relevant to the current conversation. If you say "build me a settings page that matches this Figma design," Claude might load the `design-to-code` skill automatically because the description matches.

For design enforcement, automatic activation is powerful — the design rules activate whenever design work is happening, without the user needing to remember to invoke a skill. But it requires a well-written description so Claude triggers it at the right times and not during unrelated work.

#### Skill-Scoped + Always-On Together

The best design enforcement systems use both scopes together:

- **Always-on (settings)**: Token validation, import checking, accessibility baselines. Cheap, fast, relevant to every UI file.
- **Skill-scoped**: Composition audits, cross-file consistency, Figma comparison. Expensive, thorough, only relevant during active design work.

This is layered enforcement. The always-on layer catches the obvious mechanical violations on every edit. The skill-scoped layer adds deeper, more expensive checks when the context calls for them.

### On-Demand: Skill-Instructed Scripts

These aren't hooks at all. They're scripts that live in a skill's `scripts/` directory, and the SKILL.md tells Claude to run them at appropriate moments. Claude reads the instruction, decides when it applies, and invokes the script via Bash.

```markdown
<!-- In SKILL.md body -->

## Final Verification

Before presenting any completed UI work to the user, run the full design audit:

```bash
python $CLAUDE_PROJECT_DIR/.claude/skills/design-to-code/scripts/full-audit.py --files <all modified files>
```

Fix all violations before responding. If violations remain after three attempts,
report them to the user with your recommended fixes.
```

**Use skill-instructed scripts for checks that require Claude's judgment about *when* to run them.**

Good candidates for on-demand:
- Full-page audits (too expensive for every edit, appropriate before presenting results)
- Component inventory lookup (useful when Claude is considering what to build, not on every edit)
- Design diff reports (generate a comparison document for the user to review)
- One-off validations specific to certain task types ("if building a form, run the form audit")

The tradeoff: skill-instructed scripts cost tokens to trigger (Claude reads the instruction and decides to invoke it), and they're not 100% guaranteed to run (Claude might skip the instruction under token pressure or if it seems irrelevant). But they're flexible — Claude can pass context-appropriate arguments, choose when to run them, and interpret nuanced output.

## Deciding Where to Put a Rule

Ask these questions in order:

**1. Should this rule apply to every UI file edit in the project, even when no design skill is active?**

Yes → **Settings-level hook**. Token validation, import enforcement, accessibility baselines. These are project norms, not task-specific concerns.

**2. Should this rule apply during specific design workflows but not all the time?**

Yes → **Skill-scoped hook**. Composition audits, cross-file consistency checks, Figma comparisons. These add value during design-to-code work and are wasted overhead during backend work.

**3. Is this a check that needs to run at a specific point in the workflow, with human-relevant output?**

Yes → **Skill-instructed script**. Full design reports, component inventories, diff summaries. These produce output the designer wants to see, not just pass/fail for Claude.

**4. Is this a check that should run for every developer in the organization, across all projects?**

Yes → **Managed policy settings** (organization-level) or **user settings** (`~/.claude/settings.json`) for personal cross-project standards.

### A Realistic Example

A mature design enforcement setup might look like this:

**Always-on** (`.claude/settings.json`):
- PostToolUse `Edit|Write` → `validate-tokens.py` (command handler)
- PostToolUse `Edit|Write` → `check-imports.py` (command handler)
- PreToolUse `Write` → `check-accessibility.py` (command handler)

**Skill-scoped** (in `design-to-code` skill frontmatter):
- PostToolUse `Edit|Write` → composition validator (command handler)
- Stop → cross-file consistency audit (agent handler)
- PreToolUse `Write` → component creation gatekeeper (agent handler)

**Skill-instructed** (in `design-to-code` SKILL.md body):
- "Before presenting results, run `full-audit.py`"
- "When unsure which component to use, run `component-inventory.py`"
- "After completing the page, run `diff-from-figma.py` to generate a comparison report"

Each rule lives at the scope that matches its cost, relevance, and reliability needs. The cheap, universal rules run always. The expensive, contextual rules run during design work. The human-facing reports run on demand.
