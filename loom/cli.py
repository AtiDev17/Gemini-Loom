"""gemini-loom: stateful wrapper for Gemini CLI."""

import argparse
import asyncio
from . import state, hook_writer, profiler, watchdog


def cmd_init(_args):
    """Initialize Loom in the current directory."""
    state.ensure_loom_dir()
    manifest = state.DEFAULT_MANIFEST.copy()
    state.save_manifest(manifest)
    hook_writer.install_hooks()
    print("✅ Gemini-Loom initialized. .loom/ created and hook installed.")


def cmd_account(args):
    if args.action == "add":
        profiler.add_account(args.label)
    elif args.action == "save-as":
        profiler.save_as(args.label)
    elif args.action == "list":
        accounts = profiler.list_accounts()
        active = profiler.get_active_account_label()
        if accounts:
            for a in accounts:
                marker = " (active)" if a == active else ""
                print(f" - {a}{marker}")
        else:
            print("No accounts configured.")
    elif args.action == "switch":
        profiler.switch_account(args.label)
    elif args.action == "remove":
        profiler.remove_account(args.label)
    else:
        print("Unknown account command.")


def cmd_run(args):
    prompt = args.prompt
    state.add_command(prompt)

    # Ensure active account is applied
    active = profiler.get_active_account_label()
    if active:
        profiler.switch_account(active)

    max_attempts = 3
    current_timeout = args.timeout

    for attempt in range(1, max_attempts + 1):
        runner = watchdog.GeminiRunner(prompt, timeout_seconds=current_timeout)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        exit_code, hang, rate_limited = loop.run_until_complete(runner.run())

        # Update diffs after every attempt
        diff = state.update_diff()
        if diff:
            print("📄 Diff updated for next run.")

        if rate_limited:
            print("🔄 Rate limited. Rotating account and retrying...")
            if profiler.rotate_to_next_account():
                continue
            else:
                print("❌ No alternate accounts available.")
                break

        if hang:
            print(f"⚠️ Hang occurred (timeout {current_timeout}s). Retrying with pruned context...")
            state.prune_diff()
            # double the timeout for the next attempt, capped at 10 minutes
            current_timeout = min(current_timeout * 2, 600)
            continue

        # Success
        break
    else:
        print("❌ All attempts exhausted.")


def main():
    parser = argparse.ArgumentParser(
        description="Gemini-Loom: stateful wrapper for Gemini CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize Gemini-Loom in this project")

    acc_parser = subparsers.add_parser("account", help="Manage OAuth accounts")
    acc_parser.add_argument(
        "action", choices=["add", "save-as", "list", "switch", "remove"]
    )
    acc_parser.add_argument("label", nargs="?", help="Account label")

    run_parser = subparsers.add_parser("run", help="Run a prompt through Gemini")
    run_parser.add_argument("prompt", help="The prompt to send")
    run_parser.add_argument(
        "--timeout", type=int, default=120, help="Thinking timeout in seconds"
    )

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "account":
        cmd_account(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
