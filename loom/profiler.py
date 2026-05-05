"""Manage multiple Google accounts by swapping OAuth credential files."""

import os
import shutil
from pathlib import Path
import json

GEMINI_DIR = Path.home() / ".gemini"
LOOM_ACCOUNTS_DIR = Path.home() / ".gemini-loom" / "accounts"
OAUTH_FILE = "oauth_creds.json"
ACCOUNTS_FILE = "google_accounts.json"


def ensure_accounts_store():
    LOOM_ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)


def get_active_account_label() -> str | None:
    """Read which account is currently active from .loom/manifest.json."""
    manifest_path = Path(".loom/manifest.json")
    if not manifest_path.exists():
        return None
    with open(manifest_path) as f:
        data = json.load(f)
    return data.get("active_account")


def set_active_account_label(label: str):
    """Update the manifest with active account."""
    from .state import load_manifest, save_manifest  # relative import

    manifest = load_manifest()
    manifest["active_account"] = label
    save_manifest(manifest)


def list_accounts():
    ensure_accounts_store()
    if not LOOM_ACCOUNTS_DIR.exists():
        return []
    accounts = []
    for d in LOOM_ACCOUNTS_DIR.iterdir():
        if d.is_dir():
            accounts.append(d.name)
    return accounts


def add_account(label: str):
    """Save current Gemini credentials under a label, then run 'gemini login' for a new account."""
    ensure_accounts_store()
    profile_dir = LOOM_ACCOUNTS_DIR / label
    if profile_dir.exists():
        print(f"❌ Account '{label}' already exists.")
        return

    # Backup current credentials if any
    src_oauth = GEMINI_DIR / OAUTH_FILE
    src_accounts = GEMINI_DIR / ACCOUNTS_FILE
    if src_oauth.exists() and src_accounts.exists():
        profile_dir.mkdir()
        shutil.copy2(src_oauth, profile_dir / OAUTH_FILE)
        shutil.copy2(src_accounts, profile_dir / ACCOUNTS_FILE)
        print(f"💾 Saved existing credentials as '{label}'.")
    else:
        print("ℹ️ No existing credentials found; starting fresh login.")

    # Now prompt user to login with a new account
    print(f"🔐 Please log in with the new account for '{label}'.")
    os.system("gemini login")

    # After login, save the new credentials under a 'new_' prefix temporarily
    if src_oauth.exists():
        profile_dir.mkdir(exist_ok=True)
        # move old backup aside if present
        if (profile_dir / OAUTH_FILE).exists():
            os.remove(profile_dir / OAUTH_FILE)
        if (profile_dir / ACCOUNTS_FILE).exists():
            os.remove(profile_dir / ACCOUNTS_FILE)
        shutil.copy2(src_oauth, profile_dir / OAUTH_FILE)
        shutil.copy2(src_accounts, profile_dir / ACCOUNTS_FILE)
        print(f"✅ New account '{label}' saved.")
        # Set as active
        set_active_account_label(label)
    else:
        print("❌ Login seems to have failed or no credentials written.")


def switch_account(label: str):
    """Replace current Gemini credentials with those from the given profile."""
    ensure_accounts_store()
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


def rotate_to_next_account():
    """Choose the next account that hasn't been recently rate-limited (simple round-robin)."""
    accounts = list_accounts()
    if not accounts:
        return False
    current = get_active_account_label()
    # Simple: just pick the next in list
    try:
        idx = accounts.index(current) if current in accounts else -1
    except ValueError:
        idx = -1
    next_idx = (idx + 1) % len(accounts)
    next_label = accounts[next_idx]
    return switch_account(next_label)
