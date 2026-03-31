#!/usr/bin/env python3
"""
log-hook.py — Records everything that happens during a session
===============================================================

WHAT THIS DOES:
  Keeps a running record of every action during a design-compose
  session — what the user asked, what files were read/written, what
  tools were used, and how the session ended. It's the session's
  "activity log."

WHY IT EXISTS:
  When you're building or debugging a skill, you need to see what
  happened. Did the AI read the right config files? Did it write where
  you expected? What prompt did the user give? This log answers all
  of that.

  It's also useful as a learning tool — designers building their own
  skills can look at the log to understand the sequence of events in
  a typical session.

WHEN DOES IT RUN:
  Three times:
  - When the user sends a message (UserPromptSubmit)
  - After every tool the AI uses (PostToolUse) — reads, writes, etc.
  - When the session ends (Stop)

WHERE TO SEE THE RESULTS:
  Open .claude/logs/design-compose.jsonl — each line is one event,
  written as JSON. You can open it in any text editor. The entries
  look like:

    {"timestamp": "2026-03-31T04:17:08", "event": "PostToolUse",
     "tool_name": "Write", "tool_input_summary": "Write page.tsx (10520 chars)"}

DOES THIS EVER BLOCK ANYTHING:
  No. This script always succeeds (exit code 0). It's purely for
  observation — if it crashes, the session continues normally.
  Logging should never get in the way of the actual work.

HOW IT'S CALLED:
  The SKILL.md file hooks it up to three events like this:
    python3 log-hook.py --skill design-compose --event PostToolUse

  The "--skill" flag sets the log file name (design-compose.jsonl).
  The "--event" flag tells the script what kind of event happened.
  The actual event details come through standard input as JSON.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Summarize what a tool did in one line (for readable log entries).
#
# Instead of logging the entire file contents, we just note:
#   "Write page.tsx (10520 chars)" or "Read globals.css"
# ---------------------------------------------------------------------------

def summarize_tool_input(tool_input: dict, max_len: int = 500) -> str:
    if not tool_input:
        return ""

    if "command" in tool_input:
        cmd = tool_input["command"]
        return cmd[:max_len] + ("..." if len(cmd) > max_len else "")

    if "file_path" in tool_input:
        path = tool_input["file_path"]
        if "content" in tool_input:
            return f"Write {path} ({len(tool_input['content'])} chars)"
        if "old_string" in tool_input:
            return f"Edit {path}"
        return f"Read {path}"

    if "pattern" in tool_input:
        return f"pattern='{tool_input['pattern']}'"

    s = json.dumps(tool_input)
    return s[:max_len] + ("..." if len(s) > max_len else "")


# ---------------------------------------------------------------------------
# Entry point: read the event details, build a log entry, save it.
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    parser.add_argument("--event", required=True)
    args = parser.parse_args()

    # Read the event details that Claude Code sends us
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        input_data = {"_raw_stdin": raw[:2000]}

    # Start building the log entry with common fields
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill": args.skill,
        "event": args.event,
        "session_id": input_data.get("session_id", ""),
    }

    # Add fields that are specific to each event type
    event = args.event

    if event == "UserPromptSubmit":
        # What the user typed
        entry["user_prompt"] = input_data.get("prompt", "")

    elif event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        # What tool was used and what happened
        entry["tool_name"] = input_data.get("tool_name", "")
        entry["tool_input_summary"] = summarize_tool_input(input_data.get("tool_input", {}))

        if event == "PostToolUse":
            response = input_data.get("tool_response", {})
            if isinstance(response, dict):
                resp_str = json.dumps(response)
                entry["tool_response_summary"] = resp_str[:1000] + ("..." if len(resp_str) > 1000 else "")
            elif isinstance(response, str):
                entry["tool_response_summary"] = response[:1000]

        if event == "PostToolUseFailure":
            entry["error"] = input_data.get("error", "")

    elif event == "Stop":
        # The AI's final message and whether the session ended normally
        msg = input_data.get("last_assistant_message", "")
        entry["assistant_message"] = msg[:2000] + ("..." if len(msg) > 2000 else "")
        entry["stop_hook_active"] = input_data.get("stop_hook_active", False)

    elif event in ("SessionStart", "SessionEnd"):
        entry["source"] = input_data.get("source", "")

    # Save the full raw event data too (trimmed) for debugging
    raw_str = json.dumps(input_data)
    entry["_raw"] = raw_str[:5000] + ("..." if len(raw_str) > 5000 else "")

    # Write the entry as one line in the log file
    log_dir = Path.cwd() / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{args.skill}.jsonl"

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Always exit 0 — logging should never block anything
    sys.exit(0)


if __name__ == "__main__":
    main()
