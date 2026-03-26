#!/usr/bin/env python3
"""
Universal hook logger for design skills.

Reads hook input from stdin and appends a structured log entry to
.claude/logs/design-setup.jsonl (or design-compose.jsonl).

Called by hooks with: python3 log-hook.py --skill <name> --event <event>

Logs: timestamp, event type, tool name, tool input summary, tool response
summary, user prompt, assistant message, and the full raw input.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def summarize_tool_input(tool_input: dict, max_len: int = 500) -> str:
    """Create a readable summary of tool input."""
    if not tool_input:
        return ""

    # For Bash: show the command
    if "command" in tool_input:
        cmd = tool_input["command"]
        return cmd[:max_len] + ("..." if len(cmd) > max_len else "")

    # For Edit/Write: show file path
    if "file_path" in tool_input:
        path = tool_input["file_path"]
        if "content" in tool_input:
            return f"Write {path} ({len(tool_input['content'])} chars)"
        if "old_string" in tool_input:
            return f"Edit {path}"
        return f"Read {path}"

    # For Grep/Glob
    if "pattern" in tool_input:
        return f"pattern='{tool_input['pattern']}'"

    # Fallback: JSON summary
    s = json.dumps(tool_input)
    return s[:max_len] + ("..." if len(s) > max_len else "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="Skill name (design-setup or design-compose)")
    parser.add_argument("--event", required=True, help="Hook event name")
    args = parser.parse_args()

    # Read hook input
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        input_data = {"_raw_stdin": raw[:2000]}

    # Build log entry
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill": args.skill,
        "event": args.event,
        "session_id": input_data.get("session_id", ""),
    }

    # Event-specific fields
    event = args.event

    if event == "UserPromptSubmit":
        entry["user_prompt"] = input_data.get("prompt", "")

    elif event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        entry["tool_name"] = input_data.get("tool_name", "")
        entry["tool_input_summary"] = summarize_tool_input(input_data.get("tool_input", {}))

        if event == "PostToolUse":
            response = input_data.get("tool_response", {})
            if isinstance(response, dict):
                # Summarize response (can be large)
                resp_str = json.dumps(response)
                entry["tool_response_summary"] = resp_str[:1000] + ("..." if len(resp_str) > 1000 else "")
            elif isinstance(response, str):
                entry["tool_response_summary"] = response[:1000]

        if event == "PostToolUseFailure":
            entry["error"] = input_data.get("error", "")

    elif event == "Stop":
        msg = input_data.get("last_assistant_message", "")
        entry["assistant_message"] = msg[:2000] + ("..." if len(msg) > 2000 else "")
        entry["stop_hook_active"] = input_data.get("stop_hook_active", False)

    elif event == "SessionStart":
        entry["source"] = input_data.get("source", "")

    elif event == "SessionEnd":
        entry["source"] = input_data.get("source", "")

    # Always include full raw input for debugging (truncated)
    raw_str = json.dumps(input_data)
    entry["_raw"] = raw_str[:5000] + ("..." if len(raw_str) > 5000 else "")

    # Write to log file
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{args.skill}.jsonl"

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Always exit 0 — logging should never block anything
    sys.exit(0)


if __name__ == "__main__":
    main()
