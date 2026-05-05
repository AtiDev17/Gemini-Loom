"""Manage multiple Google accounts by swapping OAuth credential files."""

import shutil
import subprocess
import time
import platform
from pathlib import Path
import json

GEMINI_DIR = Path.home() / ".gemini"
LOOM_ACCOUNTS_DIR = Path.home() / ".gemini-loom" / "accounts"
BACKUP_DIR = Path.home() / ".gemini-loom" / "backups"
ORIGINAL_BACKUP_DIR = BACKUP_DIR / "original"
OAUTH_FILE = "oauth_creds.json"
ACCOUNTS_FILE = "google_accounts.json"

_GEMINI_PS1_PATH = Path.home() / "AppData" / "Roaming" / "npm" / "gemini.ps1"


def ensure_accounts_store():
    LOOM_ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)


def _backup_original_credentials():
    """
    Create a one‑time backup of the current global .gemini credentials
    to ~/.gemini-loom/backups/original/ so they can never be accidentally lost.
    """
    if ORIGINAL_BACKUP_DIR.exists():
        return  # already backed up

    src_oauth = GEMINI_DIR / OAUTH_FILE
    src_accounts = GEMINI_DIR / ACCOUNTS_FILE
    if not src_oauth.exists() or not src_accounts.exists():
        return

    ORIGINAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_oauth, ORIGINAL_BACKUP_DIR / OAUTH_FILE)
    shutil.copy2(src_accounts, ORIGINAL_BACKUP_DIR / ACCOUNTS_FILE)
    print("🛡️  Original global credentials backed up.")


def get_active_account_label() -> str | None:
    manifest_path = Path(".loom/manifest.json")
    if not manifest_path.exists():
        return None
    with open(manifest_path) as f:
        data = json.load(f)
    return data.get("active_account")


def set_active_account_label(label: str):
    from .state import load_manifest, save_manifest

    manifest = load_manifest()
    manifest["active_account"] = label
    save_manifest(manifest)


def list_accounts():
    ensure_accounts_store()
    if not LOOM_ACCOUNTS_DIR.exists():
        return []
    return [d.name for d in LOOM_ACCOUNTS_DIR.iterdir() if d.is_dir()]


def save_current_as(label: str) -> bool:
    """Save currently active Gemini credentials as a named profile."""
    ensure_accounts_store()
    profile_dir = LOOM_ACCOUNTS_DIR / label
    if profile_dir.exists():
        print(f"❌ Account '{label}' already exists.")
        return False

    src_oauth = GEMINI_DIR / OAUTH_FILE
    src_accounts = GEMINI_DIR / ACCOUNTS_FILE
    if not src_oauth.exists() or not src_accounts.exists():
        print(
            "❌ No active credentials found. Please log in first with 'gemini login'."
        )
        return False

    profile_dir.mkdir()
    shutil.copy2(src_oauth, profile_dir / OAUTH_FILE)
    shutil.copy2(src_accounts, profile_dir / ACCOUNTS_FILE)
    set_active_account_label(label)
    print(f"💾 Saved current credentials as '{label}' (now active).")
    return True


def _gemini_command(subcommand: str):
    """Build the command list to invoke gemini with a subcommand (e.g., 'login')."""
    if platform.system() == "Windows" and _GEMINI_PS1_PATH.exists():
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_GEMINI_PS1_PATH),
            subcommand,
        ]
    else:
        return ["gemini", subcommand]


def _run_login_and_wait_for_tokens(timeout_seconds=300):
    """
    Run 'gemini login' visibly so the user can interact.
    Poll for token files; terminate the process once they appear.
    """
    oauth_file = GEMINI_DIR / OAUTH_FILE
    accounts_file = GEMINI_DIR / ACCOUNTS_FILE

    # Ensure clean state (no leftover partial tokens)
    if oauth_file.exists():
        oauth_file.unlink()
    if accounts_file.exists():
        accounts_file.unlink()

    cmd = _gemini_command("login")
    print("🔐 Starting browser authentication...")
    print("   Please complete the login in the terminal below.")
    print("   This window will close automatically once authentication is done.\n")

    proc = subprocess.Popen(cmd)

    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if proc.poll() is not None:
            break

        oauth_ok = oauth_file.exists() and oauth_file.stat().st_size > 0
        accounts_ok = accounts_file.exists() and accounts_file.stat().st_size > 0
        if oauth_ok and accounts_ok:
            time.sleep(1)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("\n✅ Authentication completed. Tokens saved.")
            return True

        elapsed = int(time.time() - start_time)
        if elapsed > 0 and elapsed % 15 == 0:
            print(f"⏳ Waiting for authentication... ({elapsed}s elapsed)")

        time.sleep(0.5)

    print("")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return oauth_file.exists() and accounts_file.exists()


def add_account(label: str):
    """
    Save current credentials as `label`, then open a browser for a new account.
    The new account will become active with an auto-generated label.
    """
    # Backup original global credentials before any destructive action
    _backup_original_credentials()

    if not save_current_as(label):
        return

    # Delete current credentials to force fresh login
    src_oauth = GEMINI_DIR / OAUTH_FILE
    src_accounts = GEMINI_DIR / ACCOUNTS_FILE
    if src_oauth.exists():
        src_oauth.unlink()
    if src_accounts.exists():
        src_accounts.unlink()

    try:
        success = _run_login_and_wait_for_tokens()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted. Restoring previous account...")
        switch_account(label)
        return

    if success:
        new_label = f"new-{int(time.time())}"
        save_current_as(new_label)
        print(f"✅ New account added as '{new_label}'.")
        print("   To rename: gemini-loom account save-as <new-name>")
    else:
        print("❌ Login timed out or failed. Restoring previous account.")
        switch_account(label)


def save_as(label: str):
    save_current_as(label)


def switch_account(label: str):
    """Activate a saved account profile."""
    ensure_accounts_store()
    _backup_original_credentials()  # safe even if already done

    profile_dir = LOOM_ACCOUNTS_DIR / label
    if not profile_dir.exists():
        print(f"❌ Account '{label}' not found.")
        return False

    src_oauth = profile_dir / OAUTH_FILE
    src_accounts = profile_dir / ACCOUNTS_FILE
    if not src_oauth.exists() or not src_accounts.exists():
        print(f"❌ Incomplete credentials in profile '{label}'.")
        return False

    GEMINI_DIR.mkdir(exist_ok=True)
    shutil.copy2(src_oauth, GEMINI_DIR / OAUTH_FILE)
    shutil.copy2(src_accounts, GEMINI_DIR / ACCOUNTS_FILE)
    set_active_account_label(label)
    print(f"✅ Switched to account '{label}'.")
    return True


def remove_account(label: str):
    ensure_accounts_store()
    profile_dir = LOOM_ACCOUNTS_DIR / label
    if not profile_dir.exists():
        print(f"❌ Account '{label}' not found.")
        return
    if get_active_account_label() == label:
        print(
            "⚠️  Warning: This account is currently active. You'll need to switch or re-login."
        )
    shutil.rmtree(profile_dir)
    print(f"🗑️  Removed account '{label}'.")


def rotate_to_next_account():
    accounts = list_accounts()
    if not accounts:
        return False
    current = get_active_account_label()
    try:
        idx = accounts.index(current) if current in accounts else -1
    except ValueError:
        idx = -1
    next_idx = (idx + 1) % len(accounts)
    next_label = accounts[next_idx]
    return switch_account(next_label)
