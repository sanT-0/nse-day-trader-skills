#!/usr/bin/env python3
"""Deterministic repository/skill validation used locally and in CI."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "nse-trader": None,
    "nse-trader-alerts": "alerts.py",
    "nse-trader-analyst": "facts.py",
    "nse-trader-broker": "ticket.py",
    "nse-trader-budget": "budget.py",
    "nse-trader-entry": "entry.py",
    "nse-trader-exit": "exit.py",
    "nse-trader-flows": "flows.py",
    "nse-trader-news": "news.py",
    "nse-trader-risk": "risk.py",
    "nse-trader-scanner": "scan.py",
    "nse-trader-timemachine": "timemachine.py",
}
ALLOWED_IMPORTS = {
    "__future__", "argparse", "collections", "csv", "datetime", "email", "hashlib", "html",
    "io", "json", "math", "nsemkt", "os", "random", "re", "sys", "time",
    "urllib", "xml",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def verify() -> list[str]:
    errors: list[str] = []
    actual = {
        path.name for path in ROOT.glob("nse-trader*")
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    if actual != set(EXPECTED):
        errors.append(
            f"skill IDs differ: missing={sorted(set(EXPECTED)-actual)}, "
            f"extra={sorted(actual-set(EXPECTED))}"
        )

    canonical = ROOT / "shared" / "nsemkt.py"
    if not canonical.is_file():
        errors.append("shared/nsemkt.py is missing")
        canonical_hash = ""
    else:
        canonical_hash = sha256(canonical)

    for skill_id, main_name in EXPECTED.items():
        directory = ROOT / skill_id
        skill_md = directory / "SKILL.md"
        notice = directory / "NOTICE.md"
        license_file = directory / "LICENSE"
        if not skill_md.is_file():
            errors.append(f"{skill_id}: SKILL.md missing")
            continue
        metadata = frontmatter(skill_md)
        if metadata.get("name") != skill_id:
            errors.append(f"{skill_id}: frontmatter name is {metadata.get('name')!r}")
        if len(metadata.get("description", "")) < 30:
            errors.append(f"{skill_id}: description is missing or too short")
        if not notice.is_file():
            errors.append(f"{skill_id}: NOTICE.md missing")
        if not license_file.is_file() or license_file.read_bytes() != (ROOT / "LICENSE").read_bytes():
            errors.append(f"{skill_id}: standalone LICENSE missing or drifted")
        if main_name is None:
            continue

        scripts = directory / "scripts"
        main_path = scripts / main_name
        shared_path = scripts / "nsemkt.py"
        if not main_path.is_file():
            errors.append(f"{skill_id}: scripts/{main_name} missing")
            continue
        if not shared_path.is_file() or (canonical_hash and sha256(shared_path) != canonical_hash):
            errors.append(f"{skill_id}: shared nsemkt.py missing or drifted")
        source = main_path.read_text(encoding="utf-8-sig")
        if "import nsemkt" not in source:
            errors.append(f"{skill_id}: main script does not import local nsemkt")
        try:
            compile(source, str(main_path), "exec")
            found = imports(main_path)
        except SyntaxError as exc:
            errors.append(f"{skill_id}: syntax error: {exc}")
            continue
        external = sorted(found - ALLOWED_IMPORTS)
        if external:
            errors.append(f"{skill_id}: non-stdlib imports: {external}")

    # Canonical module itself must remain standard-library only.
    if canonical.is_file():
        try:
            compile(canonical.read_text(encoding="utf-8-sig"), str(canonical), "exec")
            external = sorted(imports(canonical) - ALLOWED_IMPORTS)
            if external:
                errors.append(f"shared/nsemkt.py: non-stdlib imports: {external}")
        except SyntaxError as exc:
            errors.append(f"shared/nsemkt.py: syntax error: {exc}")

    assets = ROOT / "nse-trader-scanner" / "assets"
    expected_counts = {"nifty50.txt": 50, "nifty100.txt": 100, "nifty500.txt": 500}
    for name, minimum in expected_counts.items():
        path = assets / name
        if not path.is_file():
            errors.append(f"scanner asset missing: {name}")
            continue
        count = len([line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()])
        if count < minimum:
            errors.append(f"scanner asset {name}: expected at least {minimum}, got {count}")

    for metadata_path in (
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / ".claude-plugin" / "marketplace.json",
    ):
        try:
            json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            errors.append(f"invalid plugin metadata {metadata_path.name}: {exc}")

    try:
        manifest = json.loads((ROOT / "skills-manifest.json").read_text(encoding="utf-8"))
        manifest_ids = {item["id"] for item in manifest.get("skills", [])}
        if manifest_ids != set(EXPECTED):
            errors.append("skills-manifest.json IDs do not match skill directories")
        commands = []
        for item in manifest.get("skills", []):
            if item.get("command"):
                commands.append(item["command"])
                entrypoint = ROOT / str(item.get("entrypoint") or "")
                if not entrypoint.is_file():
                    errors.append(f"manifest entrypoint missing: {item.get('entrypoint')}")
        if len(commands) != len(set(commands)):
            errors.append("skills-manifest.json contains duplicate commands")
        plugin = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        if manifest.get("version") != plugin.get("version"):
            errors.append("manifest and plugin versions differ")
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"invalid skills-manifest.json: {exc}")

    # Python creates ignored __pycache__ folders during an ordinary test run;
    # those are harmless. Runtime state inside the router source directory is
    # not, because it could be mistaken for repository content.
    runtime_root = ROOT / "nse-trader"
    forbidden = []
    if (runtime_root / "cache").exists():
        forbidden.extend((runtime_root / "cache").rglob("*"))
    for pattern in ("*.json", "*.jsonl", "ticket.md", "facts.md"):
        forbidden.extend(runtime_root.glob(pattern))
    if forbidden:
        errors.append(f"runtime/cache files present: {[str(p.relative_to(ROOT)) for p in forbidden[:10]]}")

    # Exercise every CLI parser without data/network access.
    with tempfile.TemporaryDirectory(prefix="nse-skills-verify-") as tmp:
        for skill_id, main_name in EXPECTED.items():
            if main_name is None:
                continue
            command = [sys.executable, str(ROOT / skill_id / "scripts" / main_name), "--help"]
            run = subprocess.run(command, cwd=tmp, capture_output=True, text=True, timeout=30)
            if run.returncode != 0:
                errors.append(f"{skill_id}: --help failed ({run.returncode}): {run.stderr.strip()}")
    return errors


def main() -> int:
    errors = verify()
    if errors:
        print(f"FAILED: {len(errors)} verification error(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(EXPECTED)} skills, standalone copies, metadata, assets and CLIs verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
