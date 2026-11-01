from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path, local_imports: Path | None = None):
    if local_imports is not None:
        sys.path.insert(0, str(local_imports))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if local_imports is not None:
            sys.path.remove(str(local_imports))


def load_shared():
    return load_module("nse_shared_test", ROOT / "shared" / "nsemkt.py")
