"""Write the context-injecting hook into the project's Gemini settings."""

import json
from pathlib import Path

HOOK_SCRIPT_CONTENT = r'''# -*- coding: utf-8 -*-
"""Gemini-Loom: SessionStart hook to inject diff context."""
import json
import sys
from pathlib import Path

MANIFEST_PATH = Path(".loom/manifest.json")

if not MANIFEST_PATH.exists():
    print(json.dumps({"systemMessage": "Loom: no state yet."}))
    sys.exit(0)

try:
    state = json.loads(MANIFEST_PATH.read_text())
except Exception:
    sys.exit(0)

diff = state.get("last_diff", "")
commands = state.get("last_5_commands", [])

if not diff and not commands:
    sys.exit(0)

context_parts = []
if diff:
    context_parts.append(f"**CRITICAL - DO NOT RE-SCAN ENTIRE REPO.**\nRecent diff:\n```diff\n{diff}\n```")
if commands:
    context_parts.append(f"Previous tasks:\n" + "\n".join(f"- {c}" for c in commands))

context = "\n\n".join(context_parts)

print(json.dumps({
    "hookSpecificOutput": {
        "additionalContext": context
    }
}))
'''


def install_hooks():
    """Add the SessionStart hook to .gemini/settings.json."""
    settings_path = Path(".gemini/settings.json")
    hooks_dir = Path(".loom/hooks")
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Write the hook script
    hook_script = hooks_dir / "inject_context.py"
    hook_script.write_text(HOOK_SCRIPT_CONTENT)
    hook_script.chmod(0o755)

    # Load or create settings
    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        settings = {}

    if "hooks" not in settings:
        settings["hooks"] = {}
    if "SessionStart" not in settings["hooks"]:
        settings["hooks"]["SessionStart"] = []

    # Check if our hook already present
    for group in settings["hooks"]["SessionStart"]:
        for hook in group.get("hooks", []):
            if hook.get("name") == "loom-context-injector":
                return  # Already installed

    # Add hook definition
    new_hook = {
        "matcher": "",
        "hooks": [
            {
                "name": "loom-context-injector",
                "type": "command",
                "command": f"python {hook_script.absolute()}",
                "timeout": 5000,
            }
        ],
    }
    settings["hooks"]["SessionStart"].append(new_hook)

    # Ensure directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
    print("✅ Installed loom context hook.")
