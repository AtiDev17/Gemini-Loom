# Gemini-Loom

A stateful wrapper for the Google Gemini CLI that prevents infinite "Thinking…" hangs and rotates OAuth accounts automatically when rate limits hit.

## Features

- **Stateful Context Injection** – Tracks file diffs and injects them via Gemini hooks so the CLI never re-scans your entire repo.
- **Anti-Hang Watchdog** – Kills stalled processes and retries with pruned context and a longer timeout.
- **Account Rotation** – Detects 429 errors and swaps to your next Google account automatically.
- **Multi-Account Management** – Store and switch between multiple OAuth profiles.
- **Safe by Default** – Backs up your original `~/.gemini/` credentials before making any changes.
- **Zero Dependencies** – Uses only Python standard library.

## Installation

Requires Python 3.11+ and the [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed globally.

```bash
git clone https://github.com/AtiDev17/Gemini-Loom.git
cd Gemini-Loom
pip install -e .
```

## Quick Start

```bash
# 1. Initialize in your project
gemini-loom init

# 2. Add accounts (for rotation)
gemini login                          # log in with your second account
gemini-loom account save-as work
gemini login                          # log back in with your first account
gemini-loom account save-as personal

# 3. Run a prompt
gemini-loom run "fix the login bug"
```

## Commands

| Command | Description |
|---------|-------------|
| `gemini-loom init` | Initialize Loom in the current directory |
| `gemini-loom run "<prompt>"` | Run a prompt with state injection |
| `gemini-loom run "<prompt>" --timeout 30` | Run with custom hang timeout (seconds) |
| `gemini-loom account list` | List saved OAuth profiles |
| `gemini-loom account save-as <label>` | Save current credentials as a profile |
| `gemini-loom account switch <label>` | Activate a saved profile |
| `gemini-loom account remove <label>` | Delete a saved profile |

## How It Works

1. **Before execution** – Your active OAuth profile is applied.
2. **SessionStart hook** – Injects recent diffs + command history so Gemini knows what changed.
3. **Watchdog** – Monitors Gemini's output stream; kills and retries on hang.
4. **On 429** – Detects rate limits, rotates to the next account, retries.
5. **After execution** – File hashes and diffs are updated for the next run.

## License

MIT © [AtiDev17](https://github.com/AtiDev17)