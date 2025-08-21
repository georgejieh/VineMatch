from __future__ import annotations
import argparse

def main() -> None:
    """VineMatch CLI entry point."""
    parser = argparse.ArgumentParser(prog="vinematch", description="VineMatch utilities")
    sub = parser.add_subparsers(dest="cmd", required=False)

    # Example: placeholder subcommand
    ping = sub.add_parser("ping", help="Health check")
    ping.set_defaults(func=lambda _: print("VineMatch is installed and ready."))

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
