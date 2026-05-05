"""Read/Write the project state stored in .loom/manifest.json and compute file diffs."""

import json
import os
import hashlib
import difflib
from pathlib import Path

MANIFEST_PATH = ".loom/manifest.json"
SNAPSHOTS_DIR = ".loom/snapshots"

DEFAULT_MANIFEST = {
    "version": "1",
    "file_hashes": {},
    "last_diff": "",
    "last_5_commands": [],
    "active_account": "",
    "watchdog_config": {"thinking_timeout_sec": 120, "retry_strategy": "pruned"},
}

# Files/directories to always ignore
ALWAYS_IGNORE = {
    ".git",
    ".loom",
    ".gemini",
    "node_modules",
    "__pycache__",
    ".venv",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.o",
    "*.so",
    "*.dll",
    "*.exe",
    "*.bin",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.mp3",
    "*.mp4",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.rar",
}

MAX_SNAPSHOT_SIZE = 1024 * 1024  # 1 MB


def ensure_loom_dir():
    """Create .loom directory if it doesn't exist."""
    Path(".loom").mkdir(exist_ok=True)
    Path(SNAPSHOTS_DIR).mkdir(exist_ok=True)


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


def _should_ignore(path: str) -> bool:
    """Check if a path should be ignored (simple gitignore-like rules)."""
    # Check direct name matches
    name = Path(path).name
    if name in ALWAYS_IGNORE:
        return True
    # Check extension patterns like *.pyc
    suffix = Path(path).suffix
    if f"*{suffix}" in ALWAYS_IGNORE:
        return True
    # Check if any parent directory is ignored
    parts = Path(path).parts
    for part in parts:
        if part in ALWAYS_IGNORE:
            return True
    # Respect .gitignore if present (basic support)
    gitignore = Path(".gitignore")
    if gitignore.exists():
        try:
            lines = gitignore.read_text().splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Simple matching (not full gitignore spec)
                    if line.endswith("/") and path.startswith(line.rstrip("/")):
                        return True
                    if line.startswith("*.") and path.endswith(line[1:]):
                        return True
                    if path == line or path.startswith(line + "/"):
                        return True
        except Exception:
            pass
    return False


def compute_file_hashes() -> dict:
    """Walk the project directory and return {rel_path: sha256} for all non-ignored files."""
    hashes = {}
    for root, dirs, files in os.walk("."):
        # Remove ignored directories in-place to skip walking them
        dirs[:] = [d for d in dirs if not _should_ignore(os.path.join(root, d))]
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), ".")
            if _should_ignore(rel_path):
                continue
            full_path = os.path.join(root, f)
            try:
                stat = os.stat(full_path)
                if stat.st_size > MAX_SNAPSHOT_SIZE:
                    continue
                with open(full_path, "rb") as fh:
                    sha = hashlib.sha256(fh.read()).hexdigest()
                hashes[rel_path] = sha
            except Exception:
                # Permission error, etc. – skip silently
                continue
    return hashes


def _snapshot_path(rel_path: str) -> Path:
    """Return the path where a snapshot of a file is stored."""
    # Use a safe filename: replace path separators
    safe_name = rel_path.replace("/", "_").replace("\\", "_")
    return Path(SNAPSHOTS_DIR) / safe_name


def _save_snapshot(rel_path: str):
    """Copy a file into .loom/snapshots/ if it's small enough."""
    src = Path(rel_path)
    if not src.exists():
        return False
    if src.stat().st_size > MAX_SNAPSHOT_SIZE:
        return False
    dest = _snapshot_path(rel_path)
    dest.write_bytes(src.read_bytes())
    return True


def _load_snapshot(rel_path: str) -> str | None:
    """Load a previously saved snapshot content."""
    snap = _snapshot_path(rel_path)
    if snap.exists():
        return snap.read_text(encoding="utf-8", errors="replace")
    return None


def update_diff():
    """
    Compute new file hashes, generate a diff between previous and current state,
    save the diff in manifest, and store snapshots of changed files.
    Returns the generated diff string (or empty).
    """
    manifest = load_manifest()
    old_hashes = manifest.get("file_hashes", {})
    new_hashes = compute_file_hashes()

    # Determine changed, added, deleted files
    changed = []
    added = []
    deleted = []

    # Check for new/changed files
    for path, nhash in new_hashes.items():
        if path not in old_hashes:
            added.append(path)
        elif old_hashes[path] != nhash:
            changed.append(path)

    # Check for deleted files
    for path in old_hashes:
        if path not in new_hashes:
            deleted.append(path)

    # Build diff content
    diff_lines = []

    for path in sorted(added + changed):
        old_content = _load_snapshot(path)
        try:
            new_content = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if old_content is None:
            # New file – show entire content as "added"
            diff_lines.append(
                f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(new_content.splitlines())} @@\n"
                + "\n".join(f"+{line}" for line in new_content.splitlines())
            )
        else:
            diff = difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
            diff_lines.append("\n".join(diff))

        # Save new snapshot for next time
        _save_snapshot(path)

    for path in deleted:
        old_content = _load_snapshot(path)
        if old_content is not None:
            diff_lines.append(
                f"--- a/{path}\n+++ /dev/null\n@@ -1,{len(old_content.splitlines())} +0,0 @@\n"
                + "\n".join(f"-{line}" for line in old_content.splitlines())
            )
        # Remove stale snapshot
        snap = _snapshot_path(path)
        if snap.exists():
            snap.unlink()

    diff_text = "\n\n".join(diff_lines)

    # Update manifest
    manifest["file_hashes"] = new_hashes
    manifest["last_diff"] = diff_text
    save_manifest(manifest)

    return diff_text

def prune_diff(max_files: int = 3):
    """
    Trim the stored diff to only the first `max_files` distinct file patches.
    This keeps the retry context small and focused.
    """
    manifest = load_manifest()
    diff_text = manifest.get("last_diff", "")
    if not diff_text:
        return

    # Split the unified diff into per-file hunks.
    # Each file patch starts with a line like '--- a/path' or '--- /dev/null'
    chunks = []
    current_chunk = []
    for line in diff_text.splitlines():
        if line.startswith("--- ") and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
        else:
            current_chunk.append(line)
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # Keep only the first max_files distinct files
    seen_files = set()
    kept_chunks = []
    for chunk in chunks:
        # extract filename from the '---' or '+++' line
        for prefix in ("--- a/", "--- /dev/null", "+++ b/", "+++ /dev/null"):
            for line in chunk.split("\n"):
                if line.startswith(prefix):
                    fname = line[len(prefix):].strip()
                    if fname and fname not in seen_files:
                        seen_files.add(fname)
                        kept_chunks.append(chunk)
                        break
            if len(kept_chunks) >= max_files:
                break
        if len(kept_chunks) >= max_files:
            break

    if kept_chunks:
        pruned = "\n\n".join(kept_chunks)
        # Add a note that the diff was pruned
        pruned += "\n\n(Note: diff pruned to limit context after a hang.)"
        manifest["last_diff"] = pruned
    else:
        manifest["last_diff"] = ""   # no relevant chunks, clear diff entirely

    save_manifest(manifest)