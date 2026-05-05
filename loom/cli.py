"""gemini-loom: stateful wrapper for Gemini CLI."""

import argparse
import asyncio
from . import state, hook_writer, profiler, watchdog


def cmd_init(_args):
    """Initialize Loom in the current directory."""
    state.ensure_loom_dir()
    # Write empty manifest
    manifest = state.DEFAULT_MANIFEST.copy()
    state.save_manifest(manifest)
    # Install hook
    hook_writer.install_hooks()
    print("✅ Gemini-Loom initialized. .loom/ created and hook installed.")


def cmd_account(args):
    if args.action == "add":
        profiler.add_account(args.label)
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
    else:
        print("Unknown account command.")


def cmd_run(args):
    prompt = args.prompt
    state.add_command(prompt)

    # Ensure active account is applied
    active = profiler.get_active_account_label()
    if active:
        profiler.switch_account(active)

    runner = watchdog.GeminiRunner(prompt, timeout_seconds=args.timeout)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    exit_code, hang, rate_limited = loop.run_until_complete(runner.run())

    if rate_limited:
        print("🔄 Rate limited. Rotating account and retrying...")
        if profiler.rotate_to_next_account():
            print("🔄 Retrying with new account...")
            runner2 = watchdog.GeminiRunner(prompt, timeout_seconds=args.timeout)
            loop.run_until_complete(runner2.run())
        else:
            print("❌ No alternate accounts available.")

    if hang:
        print("⚠️ Hang occurred. Retrying with pruned context...")
        # TODO: prune manifest last_diff and retry
        runner3 = watchdog.GeminiRunner(prompt, timeout_seconds=args.timeout)
        loop.run_until_complete(runner3.run())


def main():
    parser = argparse.ArgumentParser(
        description="Gemini-Loom: stateful wrapper for Gemini CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    subparsers.add_parser("init", help="Initialize Gemini-Loom in this project")

    # account
    acc_parser = subparsers.add_parser("account", help="Manage OAuth accounts")
    acc_parser.add_argument("action", choices=["add", "list", "switch"])
    acc_parser.add_argument("label", nargs="?", help="Account label for add/switch")

    # run
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
