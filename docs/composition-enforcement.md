# Part 5: Composition Enforcement

This is the heart of the system. Everything else — the handler types, the hook scopes, the feedback loops — exists to serve this goal: **make Claude use what already exists instead of building from scratch.**

Designers who worked in Figma understood this instinctively. You didn't redraw a button every time you needed one. You dragged an instance from the component library, overrode the label, and moved on. The instance stayed linked to the master. Change the master, every instance updates.

Code-based design systems work the same way, in principle. A `<Button>` component is the master. Every usage is an instance. But there's no drag-and-drop, no visual library panel, no constraint that forces Claude to use the component instead of writing `<button className="...">`. That constraint has to come from handlers.

## What "Composition" Means in Practice

Composition enforcement isn't one check. It's a stack of increasingly sophisticated validations:

### Level 1: Are Design System Components Used?

The most basic check. When a design system provides `<Button>`, `<Card>`, `<Input>`, `<Dialog>`, etc., any usage of the raw HTML equivalent is a violation.

This is the import checker from Part 2. It's a command handler, it's cheap, and it catches the most common form of drift.

But it's not enough. A file can import `<Card>` and still use it wrong.

### Level 2: Are Components Used Correctly?

Using the component is step one. Using it *as designed* is step two. This means:

- **Correct props**: Using `<Button variant="secondary">` instead of `<Button className="bg-gray-200">` to get a secondary button style. The component has variants for a reason.
- **Correct children**: A `<Card>` might expect `<CardHeader>`, `<CardContent>`, and `<CardFooter>` as children, not arbitrary divs.
- **Correct composition**: A `<Dialog>` might expect `<DialogTrigger>` and `<DialogContent>` as siblings, not nested.
- **No style overrides**: Adding `className` or `style` to a design system component is usually a sign that the component doesn't support what you need — which means you should extend the component or choose a different one, not hack around it.

This level requires more than regex. A command handler can check for known anti-patterns (e.g., `className=` on components that shouldn't have it), but full prop validation requires understanding the component's API. This is where agent handlers earn their cost.

### Level 3: Are Components Composed in Established Patterns?

The highest level. Even if every individual component is used correctly, the *arrangement* can be inconsistent. A card grid on the dashboard uses `grid-cols-2 gap-4`. A card grid on the settings page uses `flex flex-col gap-6`. Both are valid layouts. But one looks like the app and the other doesn't.

Pattern-level consistency requires reading other files and comparing. This is purely agent handler territory — no script can evaluate "does this page's card arrangement look like the other pages' card arrangements?" without reading those other pages.

## Building the Composition Stack

### Level 1 Handler: Component Import Checker (Command)

This handler runs on every Edit/Write via PostToolUse. It's a project-level always-on hook.

The script maintains a **component map** — a mapping from raw HTML elements to their design system equivalents. This map is the single source of truth for "what components exist and what do they replace."

```python
#!/usr/bin/env python3
"""
Enforce design system component usage over raw HTML elements.

Reads the component map from a config file so it stays in sync with
the actual component library. The config file is the single source of
truth — when a new component is added to the design system, add it
to the map and enforcement begins immediately.
"""

import json
import sys
import re
from pathlib import Path


def load_component_map(skill_dir: str | None = None) -> dict:
    """
    Load the component map from config.

    The map file is a simple JSON object mapping raw HTML patterns
    to their design system replacements:

    {
      "<button": "Use <Button> from '@/components/ui/button'. Variants: default, secondary, outline, ghost, destructive.",
      "<input": "Use <Input> from '@/components/ui/input'. For checkboxes use <Checkbox>, for toggles use <Switch>.",
      "<select": "Use <Select> from '@/components/ui/select'.",
      "<textarea": "Use <Textarea> from '@/components/ui/textarea'.",
      "<dialog": "Use <Dialog> from '@/components/ui/dialog'. Compose with <DialogTrigger>, <DialogContent>, <DialogHeader>.",
      "<table": "Use <DataTable> from '@/components/ui/data-table'. For simple tables use <Table> with <TableHeader>, <TableBody>, <TableRow>, <TableCell>.",
      "<a ": "Use <Link> from '@/components/ui/link' for internal navigation. Use <a> only for external links with target='_blank'."
    }
    """
    search_paths = []
    if skill_dir:
        search_paths.append(Path(skill_dir) / "config" / "component-map.json")
    search_paths.append(Path.cwd() / ".claude" / "config" / "component-map.json")

    for path in search_paths:
        if path.exists():
            return json.loads(path.read_text())

    # Fallback: minimal default map
    return {
        "<button": "Use <Button> from the design system",
        "<input": "Use <Input> from the design system",
        "<select": "Use <Select> from the design system",
    }


def main():
    input_data = json.load(sys.stdin)

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    path = Path(file_path)

    # Only check UI files
    if path.suffix not in {".tsx", ".jsx", ".vue", ".svelte"}:
        sys.exit(0)

    # Don't check the design system's own source files
    # Adjust these paths to match your project structure
    skip_dirs = {"components/ui", "components/primitives", "design-system"}
    if any(d in str(path) for d in skip_dirs):
        sys.exit(0)

    if not path.exists():
        sys.exit(0)

    content = path.read_text()
    component_map = load_component_map()
    violations = []

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()

        # Skip comments and JSX comments
        if stripped.startswith("//") or stripped.startswith("{/*") or stripped.startswith("*"):
            continue

        for raw_element, replacement in component_map.items():
            if raw_element.lower() in line.lower():
                violations.append(
                    f"Line {line_num}: found `{raw_element.strip()}` — {replacement}"
                )

    if not violations:
        sys.exit(0)

    feedback = (
        f"Component violations in {file_path}:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nUse design system components instead of raw HTML. "
        + "This ensures consistent styling, accessibility defaults, and behavior."
    )

    print(feedback, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
```

The component map config file is important. Rather than hardcoding the component list in the script, externalizing it means:
- The map updates when the design system updates, without touching the validator
- The replacement messages can include available variants and composition instructions
- Different projects can use the same script with different component maps

### Level 2 Handler: Prop and Style Override Checker (Command)

This handler catches the next tier of misuse — components that are imported but used incorrectly.

```python
#!/usr/bin/env python3
"""
Check for design system component misuse:
- Style overrides on components that shouldn't have them
- Missing required composition patterns
- Direct className injection on controlled components
"""

import json
import sys
import re
from pathlib import Path


# Components that should NOT receive className or style props
# because their appearance is fully controlled by their variant system
CONTROLLED_COMPONENTS = {
    "Button", "Badge", "Input", "Select", "Switch",
    "Checkbox", "Radio", "Slider", "Toggle",
}

# Components that require specific children patterns
COMPOSITION_PATTERNS = {
    "Card": {
        "expected_children": ["CardHeader", "CardContent"],
        "optional_children": ["CardFooter", "CardDescription", "CardTitle"],
        "message": "Card should contain CardHeader and CardContent as children. See component docs.",
    },
    "Dialog": {
        "expected_children": ["DialogContent"],
        "optional_children": ["DialogTrigger", "DialogHeader", "DialogFooter", "DialogTitle", "DialogDescription"],
        "message": "Dialog should contain DialogContent. Compose with DialogTrigger, DialogHeader, etc.",
    },
    "Table": {
        "expected_children": ["TableHeader", "TableBody"],
        "optional_children": ["TableRow", "TableCell", "TableHead", "TableCaption"],
        "message": "Table should contain TableHeader and TableBody.",
    },
}


def check_style_overrides(content: str, file_path: str) -> list[str]:
    """Find style/className props on controlled components."""
    violations = []

    for line_num, line in enumerate(content.splitlines(), 1):
        for component in CONTROLLED_COMPONENTS:
            # Match <Component className=... or <Component style=...
            pattern = rf"<{component}\s[^>]*(className|style)\s*="
            if re.search(pattern, line):
                violations.append(
                    f"Line {line_num}: style override on <{component}>. "
                    f"Use the component's variant/size props instead of "
                    f"className or style. If no variant fits, the component "
                    f"may need a new variant rather than a one-off override."
                )

    return violations


def check_composition_patterns(content: str, file_path: str) -> list[str]:
    """Check that compound components are composed correctly."""
    violations = []

    for parent, config in COMPOSITION_PATTERNS.items():
        # Check if the parent component is used in this file
        if f"<{parent}" not in content:
            continue

        # Check for expected children
        for child in config["expected_children"]:
            if f"<{child}" not in content:
                violations.append(
                    f"File uses <{parent}> but is missing <{child}>. "
                    f"{config['message']}"
                )

    return violations


def main():
    input_data = json.load(sys.stdin)
    file_path = input_data.get("tool_input", {}).get("file_path", "")

    if not file_path:
        sys.exit(0)

    path = Path(file_path)

    if path.suffix not in {".tsx", ".jsx"}:
        sys.exit(0)

    # Skip design system source files
    skip_dirs = {"components/ui", "components/primitives"}
    if any(d in str(path) for d in skip_dirs):
        sys.exit(0)

    if not path.exists():
        sys.exit(0)

    content = path.read_text()

    violations = []
    violations.extend(check_style_overrides(content, file_path))
    violations.extend(check_composition_patterns(content, file_path))

    if not violations:
        sys.exit(0)

    feedback = (
        f"Component usage violations in {file_path}:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )

    print(feedback, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
```

This script catches two categories of misuse:

1. **Style overrides**: Adding `className` or `style` to components whose appearance should be controlled entirely by their variant system. If `<Button variant="secondary">` doesn't give you the look you need, the answer is to add a variant to Button, not to override it with `className="bg-gray-200"`.

2. **Broken composition**: Using `<Card>` without `<CardHeader>` and `<CardContent>`, or using `<Dialog>` without `<DialogContent>`. Compound components are designed to be composed in specific ways. Skipping pieces breaks the component's internal logic and accessibility.

### Level 3 Handler: Cross-File Pattern Audit (Agent)

This handler runs on the Stop hook, once per task. It uses an agent that can read files across the project.

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "agent",
            "prompt": "You are a design system consistency auditor. Review the files modified in this session for composition pattern consistency.\n\n1. Identify which pages or views were modified by reading the transcript or checking recent git changes.\n\n2. For each modified page, identify its primary layout pattern (grid columns, flex direction, gap values, container max-widths).\n\n3. Find 2-3 similar pages in the project (e.g., if a settings page was modified, find other settings-like or dashboard-like pages).\n\n4. Compare the layout patterns. Flag any inconsistencies:\n   - Different grid column counts for the same type of content\n   - Different gap/spacing values between similar content groups\n   - Different container widths or max-widths\n   - Different card arrangement patterns (grid vs. stack vs. masonry)\n   - Inconsistent responsive breakpoint behavior\n\n5. If inconsistencies are found, respond with {\"ok\": false, \"reason\": \"...\"} including:\n   - Which file is inconsistent and which files it should match\n   - The specific CSS/layout properties that differ\n   - What the values should be changed to\n\n6. If the patterns are consistent (or no similar pages exist to compare against), respond with {\"ok\": true}.\n\n$ARGUMENTS",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

This is the most expensive check, and the most valuable. No script can evaluate "does this page's layout feel like the rest of the app?" without reading other pages and making a judgment call. The agent handler can:

- Read the modified files
- Search for similar pages with Grep/Glob
- Read those comparison files
- Identify the layout patterns in each
- Compare and report inconsistencies

It's expensive (hundreds to thousands of tokens), but it runs once per task, and it catches the class of consistency issues that nothing else can.

## The Component Creation Gatekeeper

One of the most powerful composition enforcers doesn't check existing code — it **prevents new code from being created** without justification.

This is a PreToolUse handler on the Write tool. When Claude is about to create a new file in the components directory, the handler blocks it and asks Claude to verify that no existing component serves the same purpose.

```yaml
# In skill frontmatter
hooks:
  PreToolUse:
    - matcher: "Write"
      hooks:
        - type: agent
          prompt: >
            Claude is about to create a new file. Check if this file is a
            new UI component by examining the file path in $ARGUMENTS.

            If the file is being created in a components directory (components/,
            ui/, shared/, etc.):

            1. Search the existing component directories for components with
               similar names or purposes.
            2. Read any potentially overlapping components to understand what
               they already provide.
            3. If a similar component exists that could be extended or reused,
               respond with {"ok": false, "reason": "A similar component exists
               at [path] that provides [capabilities]. Consider using or
               extending it instead. If a new component is truly needed,
               explain why the existing one is insufficient."}
            4. If no similar component exists, respond with {"ok": true}.

            If the file is NOT a component (it's a page, utility, hook, etc.),
            respond with {"ok": true} immediately.
          timeout: 30
```

This handler embodies the composition-over-creation philosophy. It doesn't prevent component creation — it ensures Claude has *considered the alternatives first*. When the handler blocks with "A similar component exists at `components/ui/Card.tsx`," Claude is forced to either use the existing component or articulate why a new one is genuinely needed.

## The Component Inventory: A Supporting Script

The validators above work reactively — they catch problems after Claude has already written code. A **component inventory script** works proactively by giving Claude information before it starts.

This is a skill-instructed script, not a hook handler. The SKILL.md tells Claude to run it at the start of any UI building task:

```markdown
## Before Building UI

Before writing any UI code, run the component inventory to understand
what's available:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/component-inventory.py
```

Use the output to plan your implementation. Compose with existing
components wherever possible. Only create new components if the
inventory doesn't include what you need.
```

The script scans the component directories and produces a structured summary:

```python
#!/usr/bin/env python3
"""
Generate a component inventory for Claude to reference before building UI.

Scans the design system directories and outputs a structured summary of
available components, their variants, and usage patterns.
"""

import sys
import re
from pathlib import Path


def extract_component_info(file_path: Path) -> dict | None:
    """Extract component name, props, and variants from a component file."""
    content = file_path.read_text()

    # Find the exported component name
    export_match = re.search(
        r"export\s+(?:default\s+)?function\s+(\w+)|"
        r"export\s+const\s+(\w+)\s*=",
        content,
    )
    if not export_match:
        return None

    name = export_match.group(1) or export_match.group(2)

    # Find variant definitions (common in shadcn/radix style systems)
    variants = []
    variant_match = re.search(r"variants?\s*:\s*\{([^}]+)\}", content)
    if variant_match:
        variant_names = re.findall(r"(\w+)\s*:", variant_match.group(1))
        variants = variant_names

    # Find prop interface/type
    props = []
    props_match = re.search(
        rf"(?:interface|type)\s+{name}Props\s*(?:=\s*)?\{{([^}}]+)\}}", content
    )
    if props_match:
        prop_names = re.findall(r"(\w+)\s*[?:]", props_match.group(1))
        props = prop_names

    # Count usages across the project
    # (simplified — a real implementation would grep the codebase)

    return {
        "name": name,
        "file": str(file_path),
        "variants": variants,
        "props": props,
    }


def main():
    # Scan common component directories
    component_dirs = [
        Path("src/components/ui"),
        Path("src/components/shared"),
        Path("src/components/layout"),
        Path("components/ui"),
        Path("components/shared"),
        Path("components/layout"),
    ]

    components = []
    for dir_path in component_dirs:
        if not dir_path.exists():
            continue
        for file in sorted(dir_path.glob("**/*.tsx")):
            info = extract_component_info(file)
            if info:
                components.append(info)

    if not components:
        print("No design system components found.")
        print("Checked directories:", ", ".join(str(d) for d in component_dirs))
        sys.exit(0)

    # Output structured inventory
    print("# Available Design System Components\n")
    print(f"Found {len(components)} components:\n")

    for comp in components:
        print(f"## {comp['name']}")
        print(f"  File: {comp['file']}")
        if comp["variants"]:
            print(f"  Variants: {', '.join(comp['variants'])}")
        if comp["props"]:
            print(f"  Props: {', '.join(comp['props'])}")
        print()

    print("---")
    print("Use these components instead of raw HTML elements.")
    print("If you need something not listed here, check with the user before creating a new component.")


if __name__ == "__main__":
    main()
```

This script outputs something like:

```
# Available Design System Components

Found 12 components:

## Button
  File: src/components/ui/button.tsx
  Variants: variant, size
  Props: variant, size, disabled, loading, icon

## Card
  File: src/components/ui/card.tsx
  Props: variant, padding

## Dialog
  File: src/components/ui/dialog.tsx
  Props: open, onOpenChange

## Input
  File: src/components/ui/input.tsx
  Variants: variant, size
  Props: variant, size, error, label, helperText
...
```

Claude reads this output and now *knows what's available* before writing a single line of code. It's proactive guidance versus reactive correction. Both matter, but the inventory reduces how often the reactive handlers need to intervene.

## Putting the Composition Stack Together

Here's how all three levels work in concert for a single task:

**Before Claude starts** (skill-instructed):
- Component inventory runs, giving Claude a map of available components

**On every edit** (PostToolUse command handlers, always-on):
- Token validator catches hardcoded colors and spacing
- Import checker catches raw HTML elements
- Prop/composition checker catches misused components and broken compound patterns

**When Claude creates a new component file** (PreToolUse agent handler, skill-scoped):
- Creation gatekeeper searches for existing alternatives
- Blocks creation if a reusable alternative exists

**When Claude finishes** (Stop agent handler, skill-scoped):
- Cross-file pattern audit compares layout patterns against similar pages
- Sends Claude back to work if composition is inconsistent

The result: Claude starts with knowledge of what exists, gets corrected instantly when it reaches for raw HTML or misuses a component, can't create redundant components without justification, and delivers a final result that's been audited for cross-page consistency.

The designer's job is reduced to: describe what you want, review the result, make taste calls on the things that require human judgment. The mechanical consistency is handled.
