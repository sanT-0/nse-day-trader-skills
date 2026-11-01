#!/usr/bin/env python3
"""Synchronize the canonical shared/nsemkt.py into standalone skills."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shared" / "nsemkt.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def destinations() -> list[Path]:
    return sorted(
        path / "scripts" / "nsemkt.py"
        for path in ROOT.glob("nse-trader-*")
        if path.is_dir() and (path / "scripts").is_dir()
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy shared/nsemkt.py into every standalone NSE skill."
    )
    parser.add_argument(
        "--check", action="store_true", help="fail if any copy differs; do not modify files"
    )
    args = parser.parse_args()

    if not SOURCE.is_file():
        print(f"ERROR: canonical module missing: {SOURCE}", file=sys.stderr)
        return 2
    targets = destinations()
    if not targets:
        print("ERROR: no standalone skill script directories found", file=sys.stderr)
        return 2

    expected = digest(SOURCE)
    mismatches = [
        target for target in targets if not target.is_file() or digest(target) != expected
    ]
    if args.check:
        if mismatches:
            for path in mismatches:
                print(f"DRIFT: {path.relative_to(ROOT)}", file=sys.stderr)
            print("Run: python scripts/sync_shared.py", file=sys.stderr)
            return 1
        print(f"OK: {len(targets)} shared-module copies match {expected[:12]}")
        return 0

    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, target)
        print(f"updated {target.relative_to(ROOT)}")
    print(f"Synchronized {len(targets)} skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
