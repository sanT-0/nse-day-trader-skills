#!/usr/bin/env python3
"""NSE market overview: trend, breadth, volatility, sectors, and flows.

Produces a transparent 0-100 health score and dated evidence. This is market
context for research, not a buy/sell signal or allocation instruction.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import statistics
import sys

import nsemkt


HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

INDEX_SYMBOLS = {
    "nifty": ("NIFTY 50", "^NSEI"),
    "bank": ("BANK NIFTY", "^NSEBANK"),
    "vix": ("INDIA VIX", "^INDIAVIX"),
}

SECTOR_SYMBOLS = {
    "NIFTY IT": "^CNXIT",
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY METAL": "^CNXMETAL",
    "NIFTY REALTY": "^CNXREALTY",
    "NIFTY ENERGY": "^CNXENERGY",
    "NIFTY PSU BANK": "^CNXPSUBANK",
    "NIFTY INFRA": "^CNXINFRA",
}


def _change(current: float, old: float | None) -> float | None:
    if old in (None, 0):
        return None
    return (current / float(old) - 1.0) * 100.0


def _rounded(value: float | None, digits: int = 2):
    return round(value, digits) if value is not None else None


def calculate_series_metrics(label: str, symbol: str, bars: list[dict]) -> dict:
    """Calculate dated trend metrics for one index/sector series."""
    if len(bars) < 2:
        raise ValueError(f"{label}: at least 2 bars required")
    closes = [float(bar["c"]) for bar in bars]
    last = bars[-1]
    close = closes[-1]
    sma20 = nsemkt.sma(closes, 20)
    sma50 = nsemkt.sma(closes, 50)
    above20 = close > sma20 if sma20 is not None else None
    above50 = close > sma50 if sma50 is not None else None
    if above20 is True and above50 is True and sma20 is not None and sma50 is not None and sma20 > sma50:
        trend = "UPTREND"
    elif above20 is False and above50 is False and sma20 is not None and sma50 is not None and sma20 < sma50:
        trend = "DOWNTREND"
    else:
        trend = "MIXED"
    return {
        "label": label,
        "symbol": symbol,
        "date": last["t"].date().isoformat(),
        "close": round(close, 2),
        "change_1d_pct": _rounded(_change(close, closes[-2])),
        "change_5d_pct": _rounded(_change(close, closes[-6] if len(closes) >= 6 else None)),
        "change_20d_pct": _rounded(_change(close, closes[-21] if len(closes) >= 21 else None)),
        "sma20": _rounded(sma20),
        "sma50": _rounded(sma50),
        "above_sma20": above20,
        "above_sma50": above50,
        "trend": trend,
        "bars": len(bars),
    }


def calculate_stock_metrics(symbol: str, bars: list[dict]) -> dict:
    if len(bars) < 51:
        raise ValueError(f"{symbol}: fewer than 51 daily bars")
    closes = [float(bar["c"]) for bar in bars]
    close = closes[-1]
    prior20 = closes[-21:-1]
    sma20 = statistics.fmean(closes[-20:])
    sma50 = statistics.fmean(closes[-50:])
    return {
        "symbol": symbol,
        "date": bars[-1]["t"].date().isoformat(),
        "change_pct": round(_change(close, closes[-2]) or 0.0, 3),
        "above_sma20": close > sma20,
        "above_sma50": close > sma50,
        "new_high_20d": close >= max(prior20),
        "new_low_20d": close <= min(prior20),
    }


def _percent(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator) * 100.0, 1)


def calculate_breadth(rows: list[dict], expected_count: int) -> dict:
    if not rows:
        return {
            "date": None, "expected": expected_count, "valid": 0, "stale": 0,
            "coverage_pct": 0.0, "advancers": 0, "decliners": 0, "unchanged": 0,
            "advancers_pct": None, "above_sma20_pct": None,
            "above_sma50_pct": None, "new_highs_20d": 0, "new_lows_20d": 0,
            "equal_weight_change_pct": None, "median_change_pct": None,
        }
    dominant_date = Counter(row["date"] for row in rows).most_common(1)[0][0]
    current = [row for row in rows if row["date"] == dominant_date]
    changes = [float(row["change_pct"]) for row in current]
    advancers = sum(value > 0.05 for value in changes)
    decliners = sum(value < -0.05 for value in changes)
    unchanged = len(changes) - advancers - decliners
    return {
        "date": dominant_date,
        "expected": expected_count,
        "valid": len(current),
        "stale": len(rows) - len(current),
        "coverage_pct": _percent(len(current), expected_count) or 0.0,
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "advancers_pct": _percent(advancers, len(current)),
        "above_sma20_pct": _percent(sum(bool(row["above_sma20"]) for row in current), len(current)),
        "above_sma50_pct": _percent(sum(bool(row["above_sma50"]) for row in current), len(current)),
        "new_highs_20d": sum(bool(row["new_high_20d"]) for row in current),
        "new_lows_20d": sum(bool(row["new_low_20d"]) for row in current),
        "equal_weight_change_pct": round(statistics.fmean(changes), 2) if changes else None,
        "median_change_pct": round(statistics.median(changes), 2) if changes else None,
    }


def calculate_sectors(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    dominant_date = Counter(row["date"] for row in rows).most_common(1)[0][0]
    current = [row for row in rows if row["date"] == dominant_date]
    ordered = sorted(current, key=lambda row: row.get("change_1d_pct") or 0.0, reverse=True)
    changes = [float(row.get("change_1d_pct") or 0.0) for row in ordered]
    positive = sum(change > 0.05 for change in changes)
    return {
        "date": dominant_date,
        "valid": len(current),
        "stale": len(rows) - len(current),
        "positive": positive,
        "negative": sum(change < -0.05 for change in changes),
        "positive_pct": _percent(positive, len(rows)),
        "average_change_pct": round(statistics.fmean(changes), 2),
        "leaders": ordered[:3],
        "laggards": list(reversed(ordered[-3:])),
        "all": ordered,
    }


def _component(name: str, points: float, maximum: int, available: bool, detail: str) -> dict:
    return {
        "name": name,
        "points": round(points, 2) if available else None,
        "max_points": maximum,
        "available": available,
        "detail": detail,
    }


def calculate_market_score(snapshot: dict) -> dict:
    components: list[dict] = []

    nifty = snapshot.get("nifty")
    if nifty:
        points = 0.0
        points += 8 if nifty.get("above_sma20") else 0
        points += 7 if nifty.get("above_sma50") else 0
        points += 5 if nifty.get("sma20") is not None and nifty.get("sma50") is not None and nifty["sma20"] > nifty["sma50"] else 0
        change = float(nifty.get("change_1d_pct") or 0.0)
        points += 5 if change >= 1 else 3 if change >= 0 else 1 if change > -1 else 0
        components.append(_component("NIFTY trend", points, 25, True, nifty.get("trend", "MIXED")))
    else:
        components.append(_component("NIFTY trend", 0, 25, False, "missing"))

    breadth = snapshot.get("breadth")
    if breadth and breadth.get("advancers_pct") is not None:
        points = (
            float(breadth["advancers_pct"]) / 100 * 15
            + float(breadth["above_sma20_pct"]) / 100 * 10
            + float(breadth["above_sma50_pct"]) / 100 * 10
        )
        detail = f"advancers {breadth['advancers_pct']:.1f}%, above 20DMA {breadth['above_sma20_pct']:.1f}%"
        components.append(_component("Breadth", points, 35, True, detail))
    else:
        components.append(_component("Breadth", 0, 35, False, "missing"))

    vix = snapshot.get("vix")
    if vix:
        level = float(vix.get("close") or 0.0)
        level_points = 13 if level <= 12 else 11 if level <= 15 else 8 if level <= 20 else 4 if level <= 25 else 1
        change = float(vix.get("change_1d_pct") or 0.0)
        points = level_points + (2 if change <= -2 else 1 if change <= 0 else 0)
        components.append(_component("Volatility", points, 15, True, f"India VIX {level:.2f} ({change:+.2f}%)"))
    else:
        components.append(_component("Volatility", 0, 15, False, "missing"))

    bank = snapshot.get("bank")
    if bank:
        points = (4 if bank.get("above_sma20") else 0) + (3 if bank.get("above_sma50") else 0)
        change = float(bank.get("change_1d_pct") or 0.0)
        points += 3 if change >= 1 else 2 if change >= 0 else 1 if change > -1 else 0
        components.append(_component("Bank confirmation", points, 10, True, bank.get("trend", "MIXED")))
    else:
        components.append(_component("Bank confirmation", 0, 10, False, "missing"))

    sectors = snapshot.get("sectors")
    if sectors:
        average = float(sectors.get("average_change_pct") or 0.0)
        points = float(sectors.get("positive_pct") or 0.0) / 100 * 7
        points += 3 if average >= 1 else 2 if average >= 0 else 1 if average > -1 else 0
        components.append(_component("Sector participation", points, 10, True, f"{sectors['positive_pct']:.1f}% positive"))
    else:
        components.append(_component("Sector participation", 0, 10, False, "missing"))

    flows = snapshot.get("flows")
    if flows:
        fii = float(flows.get("fii_net_cr") or 0.0)
        dii = float(flows.get("dii_net_cr") or 0.0)
        combined = float(flows.get("combined_net_cr") or 0.0)
        points = (2.5 if fii > 0 else 0) + (1 if dii > 0 else 0) + (1.5 if combined > 0 else 0)
        components.append(_component("Institutional flows", points, 5, True, f"FII {fii:+,.0f} cr, DII {dii:+,.0f} cr"))
    else:
        components.append(_component("Institutional flows", 0, 5, False, "missing"))

    available = sum(item["max_points"] for item in components if item["available"])
    earned = sum(float(item["points"] or 0.0) for item in components if item["available"])
    score = round(earned / available * 100.0, 1) if available else 0.0
    zone = "RISK_ON" if score >= 75 else "POSITIVE" if score >= 60 else "NEUTRAL" if score >= 40 else "CAUTIOUS" if score >= 25 else "RISK_OFF"
    return {
        "score": score,
        "zone": zone,
        "earned_points": round(earned, 2),
        "available_points": available,
        "components": components,
    }


def load_universe(name: str) -> tuple[list[str], int]:
    path = ASSETS / f"{name}.txt"
    if not path.is_file():
        raise ValueError(f"universe asset missing: {path}")
    symbols = [line.strip().upper() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    return list(dict.fromkeys(symbols)), len(symbols)


def _fetch_metrics(label: str, symbol: str) -> dict:
    return calculate_series_metrics(label, symbol, nsemkt.yahoo_chart(symbol, "1d", "6mo")["bars"])


def fetch_core_indices(errors: list[str]) -> dict:
    result = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {
            pool.submit(_fetch_metrics, label, symbol): key
            for key, (label, symbol) in INDEX_SYMBOLS.items()
        }
        for future in as_completed(pending):
            key = pending[future]
            try:
                result[key] = future.result()
            except Exception as exc:
                errors.append(f"{INDEX_SYMBOLS[key][0]}: {exc}")
                result[key] = None
    return result


def fetch_breadth(symbols: list[str], workers: int, errors: list[str]) -> list[dict]:
    rows = []

    def one(symbol: str):
        bars = nsemkt.yahoo_chart(symbol, "1d", "3mo")["bars"]
        return calculate_stock_metrics(symbol, bars)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(one, symbol): symbol for symbol in symbols}
        for future in as_completed(pending):
            symbol = pending[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                errors.append(f"breadth {symbol}: {exc}")
    return rows


def fetch_sectors(workers: int, errors: list[str]) -> dict | None:
    rows = []
    with ThreadPoolExecutor(max_workers=min(workers, len(SECTOR_SYMBOLS))) as pool:
        pending = {
            pool.submit(_fetch_metrics, label, symbol): label
            for label, symbol in SECTOR_SYMBOLS.items()
        }
        for future in as_completed(pending):
            label = pending[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                errors.append(f"sector {label}: {exc}")
    return calculate_sectors(rows)


def _float(value) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def fetch_flows(errors: list[str]) -> dict | None:
    try:
        data = nsemkt.http_json("https://www.nseindia.com/api/fiidiiTradeReact")
        latest = {}
        for row in data if isinstance(data, list) else []:
            latest[str(row.get("category") or "").upper()] = row
        fii = latest.get("FII/FPI") or latest.get("FII")
        dii = latest.get("DII")
        if not fii and not dii:
            raise ValueError("no FII/DII records returned")
        fii_net = _float((fii or {}).get("netValue"))
        dii_net = _float((dii or {}).get("netValue"))
        return {
            "date": (fii or dii).get("date"),
            "fii_net_cr": round(fii_net, 2),
            "dii_net_cr": round(dii_net, 2),
            "combined_net_cr": round(fii_net + dii_net, 2),
        }
    except Exception as exc:
        errors.append(f"FII/DII: {exc}")
        return None


def confidence(snapshot: dict, errors: list[str], scope_pct: float) -> str:
    component_coverage = float(snapshot["score"]["available_points"])
    breadth_coverage = float((snapshot.get("breadth") or {}).get("coverage_pct") or 0.0)
    dates = {
        item.get("date") for item in (
            snapshot.get("nifty"), snapshot.get("breadth"), snapshot.get("sectors")
        ) if item and item.get("date")
    }
    dates_aligned = len(dates) <= 1
    if component_coverage >= 90 and breadth_coverage >= 85 and scope_pct >= 90 and not errors and dates_aligned:
        return "HIGH"
    if component_coverage >= 70 and breadth_coverage >= 60 and scope_pct >= 50:
        return "MEDIUM"
    return "LOW"


def interpretation(zone: str) -> str:
    return {
        "RISK_ON": "Trend and participation are broadly constructive; still validate individual setups.",
        "POSITIVE": "Conditions lean constructive, with some confirmation gaps or selective participation.",
        "NEUTRAL": "Signals are mixed; prioritize selectivity and defined risk.",
        "CAUTIOUS": "Participation or trend is weak; avoid treating isolated strength as broad confirmation.",
        "RISK_OFF": "Trend, breadth, or volatility is defensive; focus on capital preservation and evidence quality.",
    }[zone]


def build_markdown(snapshot: dict) -> str:
    score = snapshot["score"]
    lines = [
        "# NSE Market Overview", "",
        f"**Generated:** {snapshot['generated_ist']}",
        f"**Data as of:** {snapshot['as_of_date']}",
        f"**Snapshot:** {snapshot['snapshot_type']}", "",
        "## Assessment", "",
        "| Metric | Value |", "|---|---|",
        f"| Health score | **{score['score']:.1f}/100** |",
        f"| Zone | **{score['zone']}** |",
        f"| Data confidence | {snapshot['confidence']} |",
        f"| Component coverage | {score['available_points']}/100 points |",
        "", f"> {snapshot['interpretation']}", "",
        "## Index snapshot", "",
        "| Index | Close | 1D | 5D | 20D | Trend |", "|---|---:|---:|---:|---:|---|",
    ]
    for key in ("nifty", "bank", "vix"):
        row = snapshot.get(key)
        if row:
            lines.append(
                f"| {row['label']} | {row['close']:,.2f} | {row['change_1d_pct']:+.2f}% | "
                f"{(row['change_5d_pct'] if row['change_5d_pct'] is not None else 0):+.2f}% | "
                f"{(row['change_20d_pct'] if row['change_20d_pct'] is not None else 0):+.2f}% | {row['trend']} |"
            )
    breadth = snapshot.get("breadth")
    if breadth:
        lines += [
            "", "## Breadth", "",
            f"- Universe: {snapshot['universe']} ({breadth['valid']}/{breadth['expected']} current symbols)",
            f"- Advances / declines / unchanged: **{breadth['advancers']} / {breadth['decliners']} / {breadth['unchanged']}**",
            f"- Advancers: {breadth['advancers_pct'] if breadth['advancers_pct'] is not None else 0:.1f}%",
            f"- Above 20DMA: {breadth['above_sma20_pct'] if breadth['above_sma20_pct'] is not None else 0:.1f}%",
            f"- Above 50DMA: {breadth['above_sma50_pct'] if breadth['above_sma50_pct'] is not None else 0:.1f}%",
            f"- 20-day highs / lows: {breadth['new_highs_20d']} / {breadth['new_lows_20d']}",
            f"- Equal-weight / median change: {breadth['equal_weight_change_pct'] if breadth['equal_weight_change_pct'] is not None else 0:+.2f}% / {breadth['median_change_pct'] if breadth['median_change_pct'] is not None else 0:+.2f}%",
        ]
    sectors = snapshot.get("sectors")
    if sectors:
        lines += ["", "## Sector rotation", "", "| Rank | Sector | 1D | Trend |", "|---:|---|---:|---|"]
        for index, row in enumerate(sectors["all"], 1):
            lines.append(f"| {index} | {row['label']} | {row['change_1d_pct']:+.2f}% | {row['trend']} |")
    flows = snapshot.get("flows")
    if flows:
        lines += [
            "", "## Institutional cash flow", "",
            f"- Date: {flows['date']}",
            f"- FII/FPI net: Rs {flows['fii_net_cr']:+,.2f} crore",
            f"- DII net: Rs {flows['dii_net_cr']:+,.2f} crore",
            f"- Combined: Rs {flows['combined_net_cr']:+,.2f} crore",
        ]
    lines += ["", "## Score components", "", "| Component | Points | Detail |", "|---|---:|---|"]
    for item in score["components"]:
        value = f"{item['points']:.2f}/{item['max_points']}" if item["available"] else f"N/A/{item['max_points']}"
        lines.append(f"| {item['name']} | {value} | {item['detail']} |")
    if snapshot["errors"]:
        lines += ["", "## Data warnings", ""] + [f"- {error}" for error in snapshot["errors"][:25]]
    lines += [
        "", "## Limitations", "",
        "- Yahoo chart data can be delayed and live-session daily bars are provisional.",
        "- Breadth covers the selected bundled universe, not every listed NSE security.",
        "- The score describes observed conditions; it is not a forecast or trade instruction.",
        "", "Educational tooling only; verify data before making financial decisions.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze today's Indian equity market using trend, breadth, VIX, sectors, and flows."
    )
    parser.add_argument("--universe", choices=["nifty50", "nifty100"], default="nifty100")
    parser.add_argument("--limit", type=int, default=None, help="scan only the first N symbols (testing/degraded scope)")
    parser.add_argument("--workers", type=int, default=6, help="parallel market-data requests (1-16)")
    parser.add_argument("--skip-sectors", action="store_true")
    parser.add_argument("--skip-flows", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        print("REFUSED: --workers must be from 1 to 16", file=sys.stderr)
        raise SystemExit(2)
    try:
        universe, universe_total = load_universe(args.universe)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
    if args.limit is not None:
        if args.limit < 1:
            print("REFUSED: --limit must be positive", file=sys.stderr)
            raise SystemExit(2)
        universe = universe[:args.limit]

    errors: list[str] = []
    indices = fetch_core_indices(errors)
    if not indices.get("nifty"):
        print("REFUSED: NIFTY 50 data is required for a market overview", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(2)

    breadth_rows = fetch_breadth(universe, args.workers, errors)
    breadth = calculate_breadth(breadth_rows, len(universe))
    sectors = None if args.skip_sectors else fetch_sectors(args.workers, errors)
    flows = None if args.skip_flows else fetch_flows(errors)
    scoring_input = {
        **indices,
        "breadth": breadth,
        "sectors": sectors,
        "flows": flows,
    }
    score = calculate_market_score(scoring_input)
    now = nsemkt.now_ist()
    session = nsemkt.session_state(now)
    as_of = indices["nifty"]["date"]
    provisional = session["state"] in ("OPEN", "SQUAREOFF") and as_of == now.date().isoformat()
    scope_pct = round(len(universe) / universe_total * 100.0, 1) if universe_total else 0.0
    if args.limit is not None and len(universe) < universe_total:
        errors.append(f"limited breadth scope: {len(universe)}/{universe_total} symbols")

    snapshot = {
        "schema_version": "1.0",
        "generated_ist": now.isoformat(timespec="seconds"),
        "as_of_date": as_of,
        "snapshot_type": "LIVE_SESSION_PROVISIONAL" if provisional else "LAST_COMPLETED_SESSION",
        "session": session,
        "universe": args.universe,
        "universe_total": universe_total,
        "universe_scanned": len(universe),
        "scope_pct": scope_pct,
        **indices,
        "breadth": breadth,
        "sectors": sectors,
        "flows": flows,
        "score": score,
        "confidence": None,
        "confidence_basis": "source availability, date alignment, and breadth coverage; not predictive certainty",
        "interpretation": interpretation(score["zone"]),
        "errors": errors,
        "sources": {
            "indices_breadth_sectors": "Yahoo chart JSON (.NS / NSE indices)",
            "flows": "NSE fiidiiTradeReact",
            "universe": f"bundled {args.universe} constituent snapshot",
        },
    }
    snapshot["confidence"] = confidence(snapshot, errors, scope_pct)
    out_dir = args.out or nsemkt.STATE_DIR
    json_path = nsemkt.save_json(os.path.join(out_dir, "market.json"), snapshot)
    markdown = build_markdown(snapshot)
    md_path = os.path.join(out_dir, "market.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    print(f"NSE MARKET  {as_of}  {snapshot['snapshot_type']}")
    print(f"  score       : {score['score']:.1f}/100 ({score['zone']})")
    print(f"  data confidence: {snapshot['confidence']}")
    print(f"  NIFTY 50    : {indices['nifty']['close']:,.2f} ({indices['nifty']['change_1d_pct']:+.2f}%)")
    if indices.get("bank"):
        print(f"  BANK NIFTY  : {indices['bank']['close']:,.2f} ({indices['bank']['change_1d_pct']:+.2f}%)")
    if indices.get("vix"):
        print(f"  INDIA VIX   : {indices['vix']['close']:,.2f} ({indices['vix']['change_1d_pct']:+.2f}%)")
    print(f"  breadth     : {breadth['advancers']}/{breadth['decliners']}/{breadth['unchanged']} A/D/U, {breadth['coverage_pct']:.1f}% coverage")
    print(f"  interpretation: {snapshot['interpretation']}")
    if errors:
        print(f"  warnings    : {len(errors)} (see report)")
    print(f"  JSON        : {json_path}")
    print(f"  Markdown    : {md_path}")


if __name__ == "__main__":
    main()
