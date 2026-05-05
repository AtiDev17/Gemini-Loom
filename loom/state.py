"""Read/Write the project state stored in .loom/manifest.json"""

import json
import os
from pathlib import Path

MANIFEST_PATH = ".loom/manifest.json"

DEFAULT_MANIFEST = {
    "version": "1",
    "file_hashes": {},
    "last_diff": "",
    "last_5_commands": [],
    "active_account": "",
    "watchdog_config": {"thinking_timeout_sec": 120, "retry_strategy": "pruned"},
}


def ensure_loom_dir():
    """Create .loom directory if it doesn't exist."""
    Path(".loom").mkdir(exist_ok=True)


def load_manifest() -> dict:
    """Load manifest, creating default if missing."""
    ensure_loom_dir()
    if not os.path.exists(MANIFEST_PATH):
        save_manifest(DEFAULT_MANIFEST)
        return DEFAULT_MANIFEST.copy()
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


def save_manifest(data: dict):
    ensure_loom_dir()
    with open(MANIFEST_PATH, "w") as f:
        json.dump(data, f, indent=2)


def add_command(command: str):
    """Record a new command and trim history to 5."""
    manifest = load_manifest()
    commands = manifest.get("last_5_commands", [])
    commands.append(command)
    if len(commands) > 5:
        commands = commands[-5:]
    manifest["last_5_commands"] = commands
    save_manifest(manifest)
