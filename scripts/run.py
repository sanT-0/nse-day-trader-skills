#!/usr/bin/env python3
"""Platform-neutral command dispatcher for every executable NSE skill."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "skills-manifest.json"


def commands() -> dict[str, Path]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        item["command"]: ROOT / item["entrypoint"]
        for item in data["skills"]
        if item.get("command") and item.get("entrypoint")
    }


def usage(mapping: dict[str, Path]) -> None:
    print("Usage: python scripts/run.py <command> [command arguments]")
    print("Commands:")
    for name in sorted(mapping):
        print(f"  {name:<12} {mapping[name].relative_to(ROOT)}")
    print("\nExample: python scripts/run.py scanner --mode daily --universe nifty100")


def main() -> int:
    mapping = commands()
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "--list"):
        usage(mapping)
        return 0
    command = sys.argv[1].lower()
    if command not in mapping:
        print(f"ERROR: unknown command {command!r}", file=sys.stderr)
        usage(mapping)
        return 2
    env = os.environ.copy()
    if "NSE_TRADER_STATE_DIR" not in env and Path.cwd().resolve() == ROOT:
        env["NSE_TRADER_STATE_DIR"] = str(ROOT / ".runtime" / "nse-trader")
        print(f"State: {env['NSE_TRADER_STATE_DIR']}")
    result = subprocess.run(
        [sys.executable, str(mapping[command]), *sys.argv[2:]], env=env
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
