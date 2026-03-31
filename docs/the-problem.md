# Part 1: The Problem

## Why AI-Driven Design Drifts

Design tools like Figma enforce consistency through constraints you never think about. A spacing grid snaps elements into place. A shared color style updates everywhere at once. A component instance inherits its parent's structure. These aren't decisions a designer makes each time — they're decisions the tool makes *for* them, invisibly, thousands of times a day.

Claude Code has none of this. It starts every session with a blank understanding of your design system. It doesn't know that your cards use 16px padding, that your primary blue is `var(--color-primary)`, or that you already have a `<Button>` component with five carefully considered variants. Unless you tell it — every time — it will make reasonable but inconsistent choices. It will pick `#3B82F6` in one file and `blue-500` in another. It will build a card with 12px padding here and 20px there. Not because it's bad at design, but because it has no persistent memory of *your* design.

This is the fundamental gap: **Figma encodes taste into the tool. Claude Code, by default, does not.**

## The Composition Trap

There's a subtler problem. When you ask Claude to build a settings page, its instinct is to *create*. It will write fresh markup — a new card layout, a new form group, a new button style — because generating code is what it's trained to do. It doesn't naturally ask "what already exists that I should use?"

This is backwards from how experienced designers work. A designer with a mature system spends most of their time *composing* — assembling existing components into new arrangements. Creating a new component is a deliberate, considered act, usually preceded by the question: "Can I do this with what we already have?"

Without enforcement, Claude will:

- Create a `<div className="card bg-white rounded-lg shadow p-4">` when a `<Card>` component already exists
- Write inline button styles when `<Button variant="secondary">` would do exactly what's needed
- Build a custom modal from scratch when `<Dialog>` is right there in the component library
- Reimplement a form layout pattern that's already established in three other pages

Each of these individually seems fine. The code works. But over a week of building, you end up with a codebase where the "same" card looks slightly different in six places, where there are three subtly different button implementations, where the settings page doesn't quite feel like the dashboard even though you can't point to why.

**This is how design systems die** — not through one bad decision, but through a thousand small ones where someone reached for raw HTML instead of the component that was already there.

## The Token Tax

Every design rule you put in a SKILL.md file or CLAUDE.md costs tokens. Not just once — on every prompt, because it sits in context. A thorough design system guide might be 3,000-5,000 tokens. That's context window space you're paying for constantly, and it scales with every rule you add.

Worse, it's unreliable. Claude *usually* follows instructions in context, but "usually" isn't good enough for design consistency. If you have 40 design rules in a SKILL.md, Claude might follow 38 of them on a given generation. The two it misses are different each time. You end up reviewing every output against a mental checklist, which defeats the purpose of using AI to move faster.

The token economics break down like this:

**Pure instruction approach (expensive, unreliable):**
- 4,000 tokens of design rules loaded every prompt
- Claude follows most of them, misses some unpredictably
- You review, catch errors, re-prompt with corrections
- Cost: high token usage + your review time + correction prompts

**Script and handler approach (cheap, deterministic):**
- 500 tokens of high-level design philosophy in SKILL.md
- Deterministic scripts enforce the mechanical rules (tokens, spacing, imports) at zero token cost
- Prompt/agent handlers enforce the judgment calls at low token cost, only when triggered
- Claude gets instant, specific feedback on violations and fixes them automatically
- Cost: low token usage + no review for scripted rules + automatic correction

The scripts don't just save tokens — they change the economics of what's *possible*. You can enforce 200 rules via scripts without adding a single token to context. Try putting 200 rules in a SKILL.md and see what happens.

## The Feedback Gap

In Figma, feedback is instant and visual. You drag an element off-grid and the guides turn red. You pick a color outside your palette and it stands out in the styles panel. The feedback loop is tight: action, feedback, correction, all within a second.

Claude Code's default feedback loop is: Claude generates code, you read it, you notice a problem, you type a correction, Claude regenerates. That loop takes minutes, not seconds. And it depends entirely on you — the human — catching every inconsistency.

Scripts and handlers close this gap by creating **automated feedback loops** that operate at machine speed:

1. Claude writes code
2. A handler fires and checks it instantly
3. If it violates a rule, Claude gets specific feedback ("line 12: replace `#fff` with `var(--surface-primary)`")
4. Claude fixes it immediately
5. The handler fires again, confirms the fix
6. Claude moves on

This loop happens in seconds, catches everything the script checks for, and requires zero human attention for mechanical rules. It frees the designer to focus on the things that actually require taste — layout decisions, interaction patterns, visual hierarchy — rather than policing token usage and import statements.

## What This Document Covers

The rest of this guide is about closing these gaps: making Claude Code enforce design consistency the way Figma does — automatically, invisibly, and reliably. We do this through **handlers** (the things that run) attached to **hooks** (the events that trigger them), combined with **skill-instructed scripts** (things Claude runs when told to).

The goal isn't to turn Claude into a worse version of a linter. It's to encode *design taste* — the accumulated decisions that make an app feel coherent — into a system that scales across sessions, across team members, and across thousands of components. Scripts handle the rules. Handlers handle the judgment. The designer handles the vision.
