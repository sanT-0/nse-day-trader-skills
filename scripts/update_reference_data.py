#!/usr/bin/env python3
"""Refresh bundled Nifty constituent lists from official NSE archive CSVs."""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import sys
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SCANNER_ASSETS = ROOT / "nse-trader-scanner" / "assets"
MARKET_ASSETS = ROOT / "nse-trader-market" / "assets"
SOURCES = {
    "nifty50.txt": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "nifty100.txt": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty500.txt": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
}
UA = "Mozilla/5.0 (compatible; nse-day-trader-skills reference updater)"


def fetch_symbols(url: str) -> list[str]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8-sig", "replace")
    rows = csv.DictReader(io.StringIO(text))
    symbols = []
    seen = set()
    for row in rows:
        symbol = str(row.get("Symbol") or row.get("SYMBOL") or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        raise RuntimeError(f"no Symbol column/data returned by {url}")
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh bundled official NSE index constituents.")
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args()
    drift = False
    for filename, url in SOURCES.items():
        try:
            symbols = fetch_symbols(url)
        except Exception as exc:
            print(f"ERROR {filename}: {exc}", file=sys.stderr)
            return 2
        new_text = "\n".join(symbols) + "\n"
        targets = [SCANNER_ASSETS / filename]
        if filename in ("nifty50.txt", "nifty100.txt"):
            targets.append(MARKET_ASSETS / filename)
        for path in targets:
            old_text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
            changed = old_text.replace("\r\n", "\n") != new_text
            drift = drift or changed
            print(
                f"{path.relative_to(ROOT)}: {len(symbols)} symbols "
                f"({'changed' if changed else 'unchanged'})"
            )
            if changed and not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(new_text)
    if args.check and drift:
        print("Reference-data drift detected; run without --check and review the diff.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
