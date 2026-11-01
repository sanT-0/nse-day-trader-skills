#!/usr/bin/env python3
"""Watch an NSE setup and identify the first completed breakout bar.

The default trigger is a close above the first 15 minutes' high, confirmed by
volume. A custom level can replace the opening-range high. The script is
read-only: it writes ./nse-trader/entry.json and never sends an order.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import nsemkt


def group_sessions(bars: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for bar in bars:
        t = bar["t"]
        if t.weekday() >= 5 or not (dt.time(9, 15) <= t.time() <= dt.time(15, 30)):
            continue
        groups.setdefault(t.date().isoformat(), []).append(bar)
    for key in groups:
        groups[key].sort(key=lambda b: b["t"])
    return groups


def select_session(groups: dict[str, list[dict]], requested: str, now: dt.datetime) -> tuple[str | None, bool]:
    """Return (date, is_live_today)."""
    dates = sorted(groups)
    today = now.date().isoformat()
    if requested == "today":
        return (today if today in groups else None), today in groups
    # "last" means the latest available completed session. During an open
    # session, skip today's partial bars. After close, today is complete.
    if today in groups and now.time() < dt.time(15, 30):
        dates = [d for d in dates if d != today]
    return (dates[-1] if dates else None), False


def analyze(args) -> dict:
    ticker = args.ticker.strip().upper()
    now = nsemkt.now_ist()
    data = nsemkt.yahoo_chart(ticker, "5m", "5d")
    groups = group_sessions(data["bars"])
    day, live_today = select_session(groups, args.session, now)
    expiry = f"{now.date().isoformat()}T15:00:00+05:30"

    if day is None:
        ss = nsemkt.session_state(now)
        status = "NOT_OPEN" if args.session == "today" and ss["state"] in (
            "PRE_MARKET", "PRE_OPEN", "WEEKEND", "HOLIDAY"
        ) else "CLOSED"
        return {
            "generated_ist": now.isoformat(timespec="seconds"),
            "ticker": ticker,
            "status": status,
            "session_date": None,
            "or_high": None, "or_low": None, "or_mid": None,
            "level": args.level, "last_price": None,
            "triggered_at": None, "trigger_price": None, "vol_ratio": None,
            "expiry": expiry,
            "note": f"no {args.session} 5-minute session is available; NSE state is {ss['state']}",
        }

    bars = groups[day]
    start = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(9, 15), nsemkt.IST)
    or_end = start + dt.timedelta(minutes=args.or_minutes)
    opening = [b for b in bars if start <= b["t"] < or_end]
    if not opening:
        raise ValueError(f"no opening-range bars for {day}")

    # Yahoo can expose the still-forming current bar. Only a bar whose full
    # five minutes elapsed may trigger a live entry.
    if live_today:
        completed = [b for b in bars if b["t"] + dt.timedelta(minutes=5) <= now]
    else:
        completed = bars
    candidates = [b for b in completed if b["t"] >= or_end]

    or_high = max(b["h"] for b in opening)
    or_low = min(b["l"] for b in opening)
    or_mid = (or_high + or_low) / 2.0
    level = float(args.level) if args.level is not None else or_high
    trigger = None
    trigger_ratio = None

    for bar in candidates:
        previous = [x["v"] for x in completed if x["t"] < bar["t"]][-10:]
        avg_vol = sum(previous) / len(previous) if previous else 0.0
        ratio = bar["v"] / avg_vol if avg_vol else 0.0
        volume_ok = args.min_vol_ratio <= 0 or ratio >= args.min_vol_ratio
        if bar["c"] > level and volume_ok:
            trigger = bar
            trigger_ratio = ratio
            break

    last = completed[-1] if completed else bars[-1]
    ss = nsemkt.session_state(now)
    if trigger:
        status = "TRIGGERED"
        note = (
            f"completed 5-minute close above {level:.2f} on {day}; "
            f"volume {trigger_ratio:.2f}x prior-10 average"
        )
    elif day != now.date().isoformat() or args.session == "last":
        status = "CLOSED"
        note = f"no qualifying breakout in the completed session {day}"
    elif now.time() >= dt.time(15, 0):
        status = "EXPIRED"
        note = "no trigger before the 15:00 new-entry cutoff"
    elif ss["state"] in ("PRE_MARKET", "PRE_OPEN", "WEEKEND", "HOLIDAY"):
        status = "NOT_OPEN"
        note = f"NSE is {ss['state'].lower()}"
    else:
        status = "WAITING"
        distance = level - last["c"]
        note = f"waiting; last close is {distance:.2f} below trigger" if distance >= 0 else (
            "price is above the level but the volume/close confirmation has not qualified"
        )

    return {
        "generated_ist": now.isoformat(timespec="seconds"),
        "ticker": ticker,
        "status": status,
        "session_date": day,
        "or_high": round(or_high, 2),
        "or_low": round(or_low, 2),
        "or_mid": round(or_mid, 2),
        "level": round(level, 2),
        "last_price": round(last["c"], 2),
        "triggered_at": trigger["t"].isoformat(timespec="minutes") if trigger else None,
        "trigger_price": round(trigger["c"], 2) if trigger else None,
        "vol_ratio": round(trigger_ratio, 2) if trigger_ratio is not None else None,
        "expiry": f"{day}T15:00:00+05:30",
        "note": note,
        "data_note": "Yahoo NSE bars may be delayed; confirm the trigger in your broker.",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Check an NSE opening-range or level breakout entry.")
    p.add_argument("--ticker", required=True, help="NSE symbol, e.g. RELIANCE")
    p.add_argument("--level", type=float, default=None,
                   help="custom trigger level; default is opening-range high")
    p.add_argument("--or-minutes", type=int, default=15,
                   help="opening-range length in minutes (default 15)")
    p.add_argument("--min-vol-ratio", type=float, default=1.2,
                   help="trigger volume / prior-10 average; 0 disables (default 1.2)")
    p.add_argument("--session", choices=["last", "today"], default="today")
    p.add_argument("--once", action="store_true",
                   help="one check (default behavior; retained for workflow clarity)")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    if args.or_minutes < 5 or args.or_minutes > 120 or args.or_minutes % 5:
        print("REFUSED: --or-minutes must be a 5-minute multiple from 5 to 120", file=sys.stderr)
        sys.exit(2)
    if args.level is not None and args.level <= 0:
        print("REFUSED: --level must be positive", file=sys.stderr)
        sys.exit(2)

    try:
        result = analyze(args)
    except (ValueError, RuntimeError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)

    out_dir = args.out or nsemkt.STATE_DIR
    path = nsemkt.save_json(os.path.join(out_dir, "entry.json"), result)
    print(f"{result['status']}  {result['ticker']}")
    if result["or_high"] is not None:
        print(f"  session/OR : {result['session_date']}  {result['or_low']:.2f}-"
              f"{result['or_high']:.2f}  midpoint {result['or_mid']:.2f}")
        print(f"  trigger     : {result['level']:.2f}  last {result['last_price']:.2f}")
    if result["triggered_at"]:
        print(f"  fired       : {result['triggered_at']} at {result['trigger_price']:.2f}  "
              f"volume {result['vol_ratio']:.2f}x")
    print(f"  note        : {result['note']}")
    print(f"  saved       : {path}")


if __name__ == "__main__":
    main()
