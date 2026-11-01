#!/usr/bin/env python3
"""Build portable ZIP archives for one or every SKILL.md directory."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def skill_dirs() -> list[Path]:
    return sorted(
        path for path in ROOT.glob("nse-trader*")
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def package(source: Path, output: Path) -> Path:
    destination = output / f"{source.name}.zip"
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            relative = Path(source.name) / path.relative_to(source)
            info = zipfile.ZipInfo(str(relative).replace("\\", "/"))
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Package portable NSE skill ZIP files.")
    parser.add_argument("--skill", help="one exact skill ID; default packages all")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    available = {path.name: path for path in skill_dirs()}
    if args.skill and args.skill not in available:
        parser.error(f"unknown skill {args.skill!r}")
    selected = [available[args.skill]] if args.skill else list(available.values())
    sums = []
    for source in selected:
        archive = package(source, args.out)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        sums.append(f"{digest}  {archive.name}")
        print(f"built {archive}")
    (args.out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
