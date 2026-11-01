#!/usr/bin/env python3
"""One-shot NSE price, stop, target, bell and flat-by alerts.

Alerts persist in ./nse-trader/alerts.json and fire once. Price checks use the
Yahoo chart endpoint and are deliberately disabled while NSE is closed so a
stale weekend quote cannot ring an alert.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

import nsemkt


def path_for(out: str | None) -> str:
    return os.path.join(out or nsemkt.STATE_DIR, "alerts.json")


def load(path: str) -> dict:
    state = nsemkt.load_json(path) or {"alerts": [], "updated_ist": None}
    state.setdefault("alerts", [])
    return state


def save(path: str, state: dict) -> None:
    state["updated_ist"] = nsemkt.now_ist().isoformat(timespec="seconds")
    nsemkt.save_json(path, state)


def alert_id(ticker: str, kind: str, level, due: str | None) -> str:
    raw = f"{ticker}|{kind}|{level}|{due}|{nsemkt.now_ist().isoformat()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def next_due(hm: str, now: dt.datetime) -> dt.datetime:
    try:
        hour, minute = (int(x) for x in hm.split(":"))
        target_time = dt.time(hour, minute)
    except (ValueError, TypeError):
        raise ValueError("time must be HH:MM")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must be HH:MM")
    if nsemkt.is_trading_day(now.date()) and now.time() < target_time:
        day = now.date()
    else:
        day = nsemkt.next_trading_day(now.date())
    return dt.datetime.combine(day, target_time, nsemkt.IST)


def add_command(args) -> int:
    now = nsemkt.now_ist()
    ticker = (args.ticker or "MARKET").strip().upper()
    plan = nsemkt.load_json(os.path.join(args.out or nsemkt.STATE_DIR, "plan.json")) or {}
    kind: str
    level = None
    due = None
    direction = None

    if args.stop:
        if not plan or plan.get("stop") is None:
            raise ValueError("no plan.json stop; pass --level or run nse-trader-exit")
        ticker = str(plan.get("ticker") or ticker).upper()
        level = float(plan["stop"])
        kind, direction = "STOP", "below"
    elif args.target:
        if not plan or plan.get("target") is None:
            raise ValueError("no plan.json target; pass --level or run nse-trader-exit")
        ticker = str(plan.get("ticker") or ticker).upper()
        level = float(plan["target"])
        kind, direction = "TARGET", "above"
    elif args.level is not None:
        if ticker == "MARKET":
            raise ValueError("--ticker is required with --level")
        q = nsemkt.yahoo_quote(ticker)
        level = float(args.level)
        direction = "above" if level >= q["ltp"] else "below"
        kind = "ABOVE" if direction == "above" else "BELOW"
    elif args.pct is not None:
        if ticker == "MARKET":
            raise ValueError("--ticker is required with --pct")
        q = nsemkt.yahoo_quote(ticker)
        level = nsemkt.round_tick(q["prev_close"] * (1 + args.pct / 100.0))
        direction = "above" if args.pct >= 0 else "below"
        kind = "PCT_MOVE"
    elif args.bell:
        kind = "BELL"
        due = next_due("09:15", now).isoformat(timespec="seconds")
        ticker = "NSE"
    elif args.flatby:
        kind = "FLAT_BY"
        due = next_due(args.flatby, now).isoformat(timespec="seconds")
        ticker = ticker if ticker != "MARKET" else str(plan.get("ticker") or "PORTFOLIO").upper()
    else:  # guarded by argparse
        raise ValueError("choose one alert type")

    path = path_for(args.out)
    state = load(path)
    # Same active or fired level is not silently re-armed. Change the level or
    # clear it first; this prevents alert spam.
    same = next((a for a in state["alerts"]
                 if a.get("ticker") == ticker and a.get("kind") == kind
                 and a.get("level") == level and a.get("due_ist") == due), None)
    if same:
        print(f"UNCHANGED  alert {same['id']} already exists ({same['status']})")
        print(f"saved: {path}")
        return 0

    record = {
        "id": alert_id(ticker, kind, level, due),
        "ticker": ticker,
        "kind": kind,
        "direction": direction,
        "level": round(level, 2) if level is not None else None,
        "due_ist": due,
        "note": args.note or "",
        "created_ist": now.isoformat(timespec="seconds"),
        "fired_at": None,
        "status": "ACTIVE",
    }
    state["alerts"].append(record)
    save(path, state)
    detail = f"{record['direction']} {record['level']:.2f}" if level is not None else due
    print(f"ADDED  {record['id']}  {ticker}  {kind}  {detail}")
    print(f"saved: {path}")
    return 0


def check_command(args) -> int:
    path = path_for(args.out)
    state = load(path)
    now = nsemkt.now_ist()
    ss = nsemkt.session_state(now)
    active = [a for a in state["alerts"] if a.get("status") == "ACTIVE"]
    quotes: dict[str, dict] = {}
    fired: list[dict] = []
    errors: list[str] = []

    for alert in active:
        kind = alert.get("kind")
        should_fire = False
        detail = ""
        if kind in ("BELL", "FLAT_BY"):
            try:
                due = dt.datetime.fromisoformat(alert["due_ist"])
                should_fire = now >= due and nsemkt.is_trading_day(due.date())
                detail = f"due {alert['due_ist']}"
            except (ValueError, TypeError):
                errors.append(f"{alert.get('id')}: malformed due time")
        elif ss["state"] in ("OPEN", "SQUAREOFF"):
            ticker = alert["ticker"]
            try:
                if ticker not in quotes:
                    quotes[ticker] = nsemkt.yahoo_quote(ticker)
                ltp = quotes[ticker]["ltp"]
                direction = alert.get("direction")
                level = float(alert["level"])
                should_fire = ltp >= level if direction == "above" else ltp <= level
                detail = f"LTP {ltp:.2f} vs {direction} {level:.2f}"
            except Exception as e:
                errors.append(f"{alert.get('id')}: {e}")
        else:
            detail = f"not checked: NSE state {ss['state']}"

        if should_fire:
            alert["status"] = "FIRED"
            alert["fired_at"] = now.isoformat(timespec="seconds")
            alert["fire_detail"] = detail
            fired.append(alert)

    save(path, state)
    for alert in fired:
        print(f"FIRED  {alert['id']}  {alert['ticker']}  {alert['kind']}  "
              f"{alert.get('fire_detail', '')}  {alert.get('note', '')}")
    summary = {
        "checked_ist": now.isoformat(timespec="seconds"),
        "nse_state": ss["state"],
        "active_checked": len(active),
        "fired": len(fired),
        "errors": errors,
    }
    print(json.dumps(summary, indent=2))
    print(f"saved: {path}")
    return 0


def list_command(args) -> int:
    path = path_for(args.out)
    state = load(path)
    if not state["alerts"]:
        print("No alerts.")
    for a in state["alerts"]:
        level = f"{a.get('direction')} {a['level']:.2f}" if a.get("level") is not None else a.get("due_ist")
        print(f"{a['id']}  {a['status']:<6}  {a['ticker']:<12} {a['kind']:<9} {level}")
    print(f"saved: {path}")
    return 0


def clear_command(args) -> int:
    path = path_for(args.out)
    state = load(path)
    before = len(state["alerts"])
    if args.id:
        state["alerts"] = [a for a in state["alerts"] if a.get("id") != args.id]
    else:
        state["alerts"] = []
    removed = before - len(state["alerts"])
    save(path, state)
    print(f"CLEARED {removed} alert(s)")
    print(f"saved: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Persistent one-shot NSE price and time alerts.")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="add one alert")
    add.add_argument("--ticker", default=None)
    group = add.add_mutually_exclusive_group(required=True)
    group.add_argument("--level", type=float)
    group.add_argument("--stop", action="store_true", help="stop from plan.json")
    group.add_argument("--target", action="store_true", help="target from plan.json")
    group.add_argument("--pct", type=float, help="percent from previous close")
    group.add_argument("--bell", action="store_true", help="next NSE 09:15 bell")
    group.add_argument("--flatby", metavar="HH:MM", help="next trading-day reminder")
    add.add_argument("--note", default="")
    add.add_argument("--out", default=None)
    add.set_defaults(func=add_command)

    check = sub.add_parser("check", help="check active alerts once")
    check.add_argument("--once", action="store_true")
    check.add_argument("--out", default=None)
    check.set_defaults(func=check_command)

    ls = sub.add_parser("list", help="list all alerts")
    ls.add_argument("--out", default=None)
    ls.set_defaults(func=list_command)

    clear = sub.add_parser("clear", help="clear one ID or all alerts")
    clear.add_argument("--id", default=None)
    clear.add_argument("--out", default=None)
    clear.set_defaults(func=clear_command)
    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        code = args.func(args)
    except (ValueError, RuntimeError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit(code)


if __name__ == "__main__":
    main()
