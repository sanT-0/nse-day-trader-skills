#!/usr/bin/env python3
"""Install every portable nse-trader* folder into an agent skill directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]


def default_destination(target: str) -> Path:
    home = Path.home()
    choices = {
        "opencode": home / ".config" / "opencode" / "skills",
        "claude": home / ".claude" / "skills",
        "agents": home / ".agents" / "skills",
    }
    return choices[target]


def skill_dirs() -> list[Path]:
    return sorted(
        path for path in ROOT.glob("nse-trader*")
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}
    return ignored


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the NSE skill pack globally.")
    parser.add_argument(
        "--target", choices=["opencode", "claude", "agents"], default="opencode"
    )
    parser.add_argument(
        "--destination", type=Path,
        help="custom skill root; overrides the target's default path",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="replace existing nse-trader* directories (removes local customizations)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sources = skill_dirs()
    if not sources:
        print("ERROR: no nse-trader skills found", file=sys.stderr)
        return 2
    destination = (args.destination or default_destination(args.target)).expanduser().resolve()
    existing = [destination / source.name for source in sources if (destination / source.name).exists()]
    if existing and not args.force:
        print("ERROR: these skills already exist; use --force to replace them:", file=sys.stderr)
        for path in existing:
            print(f"  {path}", file=sys.stderr)
        return 2

    print(f"Installing {len(sources)} skills into {destination}")
    for source in sources:
        target = destination / source.name
        if args.dry_run:
            print(f"would install {source.name} -> {target}")
            continue
        destination.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=ignore)
        print(f"installed {source.name}")
    if args.dry_run:
        print("Dry run only; no files changed.")
    else:
        print("Done. Reload your agent if it does not watch skill directories automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
