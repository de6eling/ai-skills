# Part 4: The Feedback Loop

The feedback loop is where hooks stop being passive validators and start actively shaping Claude's work. A handler that blocks a bad edit is useful. A handler that blocks a bad edit *and tells Claude exactly how to fix it, and Claude fixes it, and the handler confirms the fix* — that's a design system enforcing itself.

This is the most underutilized capability in Claude Code's hook system. Most hook examples show logging, notifications, or simple blocking. The real power is in **correction cycles** — automated loops where a handler rejects work, provides specific feedback, Claude corrects, and the handler re-evaluates.

## How Correction Cycles Work

There are two distinct patterns, operating at different scales.

### Pattern 1: Per-Edit Correction (PostToolUse)

This loop runs on every file edit. It's tight, fast, and catches problems immediately.

```
Claude edits a file
  ↓
PostToolUse fires → command handler reads the file
  ↓
Handler finds violations → exits with code 2 + feedback on stderr
  ↓
Claude receives feedback → makes another edit to fix the violations
  ↓
PostToolUse fires again → command handler re-checks
  ↓
Handler finds no violations → exits with code 0
  ↓
Claude continues with next task
```

When a PostToolUse handler exits with code 2, Claude Code **blocks the tool result from being considered successful** and feeds the stderr message back to Claude as an error. Claude sees something like:

```
Design token violations in src/components/SettingsPage.tsx:
  - Line 12: hardcoded hex color — found `#ffffff`. Use `var(--surface-primary)` instead.
  - Line 34: hardcoded spacing — found `padding: 10px`. Use `p-2` (8px) or `p-3` (12px).
```

Claude treats this like any other tool error — it reads the feedback and tries to fix it. Then it edits the file again, which triggers PostToolUse again, which re-runs the validator. If the fix introduced new violations, Claude gets another round of feedback. If everything passes, exit 0, and Claude moves on.

**This loop is self-terminating.** Once all violations are fixed, the handler exits 0 and no further corrections are needed. There's no risk of infinite loops because each correction reduces the violation count.

The cost is near-zero for the validation itself (a Python script running in milliseconds), but each correction iteration costs tokens for Claude's edit. In practice, well-written feedback leads to one-shot fixes — Claude gets specific line numbers and replacement values and fixes everything in a single edit.

### Pattern 2: End-of-Task Quality Gate (Stop)

This loop runs once, when Claude thinks it's done. It's a final audit that can send Claude back to work.

```
Claude finishes and is about to respond to the user
  ↓
Stop hook fires → handler evaluates the completed work
  ↓
Handler finds issues → command handler exits with code 2 + stderr feedback
  ↓
Claude receives the feedback as its next instruction → goes back to work
  ↓
Claude finishes again → Stop hook fires again
  ↓
Handler finds no issues → exits with code 0
  ↓
Claude's response is delivered to the user
```

**Important:** For reliable re-prompting at Stop time, use a `type: command` handler (exit 2 to block, exit 0 to allow). Stop hooks with `type: prompt` use a different format (`{"decision": "block", "reason": "..."}` or `{}` to allow) and show an error message rather than re-prompting Claude — not ideal for iterative fix loops.

The Stop hook quality gate is powerful because it evaluates the *entire task*, not just one file. A command handler on the Stop hook can scan all git-modified files and catch issues that slipped through per-edit checks.

**This loop has an infinite loop risk.** If the handler keeps finding issues, Claude keeps working, which triggers more Stop hooks. The `stop_hook_active` field exists specifically for this — when it's `true`, Claude is already responding to a previous Stop hook rejection. Your handler must check this and decide whether to allow Claude to stop.

## Preventing Infinite Loops

Every Stop hook and SubagentStop hook must account for the possibility that Claude can't satisfy the handler's requirements. There are three strategies.

### Strategy 1: Check `stop_hook_active`

The simplest approach. On the second pass, let Claude stop regardless:

```python
import json
import sys

input_data = json.load(sys.stdin)

if input_data.get("stop_hook_active", False):
    # Already went through one correction cycle — let Claude stop
    sys.exit(0)

# First pass — do your validation
# ...
```

This gives you exactly one correction cycle. Claude finishes, the handler rejects and provides feedback, Claude fixes things, Claude finishes again, `stop_hook_active` is `true`, handler exits 0, done.

One cycle is often enough. The handler identifies all issues at once, Claude fixes them all, the second pass confirms the fixes.

### Strategy 2: Counter-Based Limits

If you want multiple correction cycles (some issues are only visible after others are fixed), track the count:

```python
import json
import sys
from pathlib import Path

input_data = json.load(sys.stdin)
session_id = input_data.get("session_id", "unknown")

counter_file = Path(f"/tmp/stop-hook-{session_id}.count")
count = int(counter_file.read_text()) if counter_file.exists() else 0

MAX_CYCLES = 3

if count >= MAX_CYCLES:
    # Reached the limit — let Claude stop, report remaining issues to user
    counter_file.unlink(missing_ok=True)
    remaining = run_validation()  # your validation logic
    if remaining:
        # Output remaining issues as context for the user (not as a block)
        print(json.dumps({
            "additionalContext": f"Note: {len(remaining)} design issues remain: {remaining}"
        }))
    sys.exit(0)

count += 1
counter_file.write_text(str(count))

# Run validation...
violations = run_validation()
if violations:
    print(json.dumps({"ok": False, "reason": format_violations(violations)}))
else:
    counter_file.unlink(missing_ok=True)
    sys.exit(0)
```

### Strategy 3: Diminishing Returns Check

The smartest approach — let Claude stop when corrections aren't making progress:

```python
import json
import sys
from pathlib import Path

input_data = json.load(sys.stdin)
session_id = input_data.get("session_id", "unknown")

state_file = Path(f"/tmp/stop-hook-{session_id}.json")

# Load previous violation count
prev_count = 0
if state_file.exists():
    prev_state = json.loads(state_file.read_text())
    prev_count = prev_state.get("violation_count", 0)

# Run current validation
violations = run_validation()
current_count = len(violations)

if current_count == 0:
    # All clear
    state_file.unlink(missing_ok=True)
    sys.exit(0)

if current_count >= prev_count and prev_count > 0:
    # Not making progress — let Claude stop, report to user
    state_file.unlink(missing_ok=True)
    print(json.dumps({
        "additionalContext": f"Design review found {current_count} issues that couldn't be auto-resolved."
    }))
    sys.exit(0)

# Making progress — send Claude back to fix more
state_file.write_text(json.dumps({"violation_count": current_count}))
print(json.dumps({
    "ok": False,
    "reason": format_violations(violations)
}))
```

This lets the loop run as long as each cycle reduces violations, and stops when Claude is stuck.

## Combining Per-Edit and End-of-Task Loops

The most effective design enforcement uses both loops together, with different handlers at each level:

**Per-edit loop (PostToolUse, command handler):**
- Token validation
- Import checking
- Spacing enforcement
- Raw HTML detection

These catch mechanical violations instantly. Most files pass after one correction.

**End-of-task loop (Stop, prompt or agent handler):**
- Cross-file composition consistency
- Layout pattern matching
- Visual hierarchy audit
- Overall design system compliance

These catch the things per-edit handlers can't see — patterns that only emerge when you look at the whole page or compare multiple files.

The layering matters. By the time the Stop hook runs, the per-edit handlers have already cleaned up all the mechanical issues. The Stop hook only needs to evaluate higher-level concerns. This keeps the expensive agent handler focused on judgment calls rather than wasting time finding hardcoded colors.

## Feedback Quality Determines Loop Efficiency

A correction cycle that takes one iteration is dramatically cheaper than one that takes three. The difference is almost entirely in the quality of the feedback message.

### Anatomy of Good Feedback

The feedback message (stderr for exit-2 handlers, `reason` field for prompt/agent handlers) is the only information Claude gets about what's wrong. It needs to be:

**1. Specific about location**
```
Bad:  "Found hardcoded colors"
Good: "Line 12 in src/components/Card.tsx: hardcoded color #ffffff"
```

**2. Specific about the violation**
```
Bad:  "Spacing is wrong"
Good: "Line 18: padding: 10px is not on the 8px grid. Nearest valid values: 8px (p-2) or 16px (p-4)"
```

**3. Specific about the fix**
```
Bad:  "Use a design token"
Good: "Replace #ffffff with var(--surface-primary) or the bg-surface-primary utility class"
```

**4. Comprehensive in a single pass**
```
Bad:  Report one violation at a time (causes multiple correction cycles)
Good: Report ALL violations at once (Claude fixes everything in one edit)
```

**5. Pointing to references when the fix isn't obvious**
```
"Use a spacing token from references/design-tokens.md. Available spacing values:
4px (space-1), 8px (space-2), 12px (space-3), 16px (space-4), 24px (space-6), 32px (space-8)"
```

When feedback includes the line number, the offending value, and the replacement, Claude typically fixes it in one shot. When feedback is vague, Claude guesses, which may introduce new violations, which triggers another cycle, which costs more tokens.

### Feedback for Prompt and Agent Handlers

For PreToolUse prompt/agent handlers, the response format is `{"ok": false, "reason": "..."}`. The `reason` field serves the same purpose as stderr in command handlers — it's the message Claude receives as its next instruction.

**For Stop hooks, the format is different:** prompt handlers use `{"decision": "block", "reason": "..."}` or `{}` to allow. However, we found in practice that Stop prompt handlers show an error rather than re-prompting Claude. For reliable iterative fix loops at Stop time, use a command handler (exit 2) instead.

The same principles apply regardless of handler type. Feedback should be specific, actionable, and comprehensive:

```
The settings page layout is inconsistent with the dashboard. The dashboard
uses a 2-column grid for card groups, but the settings page uses a single
column with full-width cards. Refactor the settings page to use the same
2-column grid layout established in src/pages/Dashboard.tsx (lines 45-60).
```

This kind of nuanced feedback — comparing two files and judging layout consistency — is where agent handlers shine. But the same principles apply: be specific about what's wrong, where, and how to fix it.

## The Complete Loop Architecture

Putting it all together, here's how a well-configured design enforcement system processes a single task ("build a settings page"):

```
User: "Build a settings page for user preferences"
  ↓
Claude starts writing SettingsPage.tsx
  ↓
[EDIT 1] Claude writes initial component with raw <div> and hardcoded colors
  ↓
PostToolUse → validate-tokens.py → EXIT 2
  "Line 5: #f3f4f6 → use bg-surface-secondary
   Line 12: #ffffff → use bg-surface-primary"
  ↓
PostToolUse → check-imports.py → EXIT 2
  "Line 8: raw <button> → use <Button> from @/components/ui/button
   Line 15: raw <input> → use <Input> from @/components/ui/input"
  ↓
[EDIT 2] Claude fixes tokens and imports
  ↓
PostToolUse → validate-tokens.py → EXIT 0 ✓
PostToolUse → check-imports.py → EXIT 0 ✓
  ↓
Claude continues writing, edits more files...
  ↓
[Multiple edits, each validated and corrected as needed]
  ↓
Claude finishes: "I've built the settings page..."
  ↓
Stop → agent handler audits all modified files
  ↓
Agent reads SettingsPage.tsx, compares against Dashboard.tsx and ProfilePage.tsx
  → {"ok": false, "reason": "Settings uses single-column layout but
     Dashboard and Profile both use 2-column grid. Refactor to match."}
  ↓
Claude refactors the layout
  ↓
Stop → agent handler re-audits
  → {"ok": true}
  ↓
Claude's response is delivered to the user
```

Every step in this process happens automatically. The designer asked for a settings page and got one that uses the right tokens, the right components, and the right layout pattern — without manually checking any of those things.

This is what "encoding design taste" means in practice. The mechanical rules (tokens, imports, spacing) are enforced deterministically on every edit. The judgment calls (layout consistency, composition patterns) are enforced by an agent that can read the codebase and compare. The designer focuses on what the page should *do*, and the system ensures it *looks* like everything else.
