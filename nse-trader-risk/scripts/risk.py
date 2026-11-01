#!/usr/bin/env python3
"""nse-trader-risk: PASS or BLOCK an order against NSE-day-trading limits.

Checks the ticket from nse-trader-budget before manual broker entry: a stop must
exist, the loss at the stop (fresh-price aware) must fit the per-trade limit,
reward:risk must clear the minimum, the day's total risk must fit the daily
limit, trade count and entry-window rules must hold, blocked/duplicate tickets
are rejected, and F&O margin must fit the capital.

Exit codes: 0 = PASS, 3 = BLOCK, 2 = bad input, 1 = unexpected error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import nsemkt

DEFAULT_RULES = {
    "max_loss_per_trade": None,   # defaults to the order's own max_loss
    "daily_loss_limit": None,     # defaults to 2 x max_loss_per_trade
    "max_trades_per_day": 5,
    "min_rr": 1.5,
    "entry_window": ["09:15", "15:00"],
    "flat_by": "15:15",
    "blocked_tickers": [],
    "require_stop": True,
    "margin_pct": 15,
}


def _parse_hm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def _now(args) -> dt.datetime:
    if args.now:
        return dt.datetime.strptime(args.now, "%Y-%m-%dT%H:%M").replace(tzinfo=nsemkt.IST)
    return nsemkt.now_ist()


def check(order: dict, rules: dict, now: dt.datetime, fresh_ltp: float | None,
          capital: float | None, day_loss: float) -> tuple[list[str], float]:
    """Return (reasons_to_block, risk_inr). Empty reasons = PASS."""
    reasons: list[str] = []

    def bad(msg: str) -> None:
        reasons.append(msg)

    ticker = str(order.get("ticker", "")).upper()
    qty = int(order.get("qty") or 0)
    entry = float(order.get("entry") or 0)
    stop = float(order.get("stop") or 0)
    target = float(order.get("target") or 0)
    segment = str(order.get("segment", "CASH")).upper()

    # 1. well-formed
    if not ticker:
        bad("ticket has no ticker")
    if qty <= 0:
        bad("quantity must be positive")
    if entry <= 0 or target <= 0:
        bad("entry and target must be positive")
    if segment not in ("CASH", "FNO"):
        bad(f"unknown segment {segment}")

    # 2. stop required and sane
    if rules.get("require_stop", True) and stop <= 0:
        bad("no stop - a day trade must have a stop")
    if stop > 0 and stop >= entry:
        bad(f"stop {stop:.2f} is not below entry {entry:.2f}")

    # 3. reward:risk
    risk_per_share = entry - stop
    if risk_per_share > 0 and target > 0:
        rr = (target - entry) / risk_per_share
        if rr < float(rules.get("min_rr", 1.5)) - 1e-9:
            bad(f"reward:risk {rr:.2f} is below the {rules.get('min_rr')} minimum")

    # 4. loss at the stop, from the higher of entry and a fresh price
    ref = max(entry, fresh_ltp) if fresh_ltp else entry
    risk_per_share_live = max(ref - stop, 0.0)
    if fresh_ltp and fresh_ltp > entry:
        charge_product = (
            "OPT" if segment == "FNO" and order.get("instrument") == "OPTION"
            else "FUT" if segment == "FNO" else str(order.get("product", "MIS"))
        )
        charges = nsemkt.round_trip_charges(
            segment, qty, ref, stop, charge_product,
            broker=str(order.get("broker") or "generic"),
            broker_profile=order.get("broker_profile_rules"),
        )["total"]
    else:
        charges = (order.get("charges") or {}).get("total", 0.0) or 0.0
    risk_inr = qty * risk_per_share_live + charges

    per_trade_cap = float(rules.get("max_loss_per_trade") or order.get("max_loss") or 0)
    if per_trade_cap and risk_inr > per_trade_cap + 1e-6:
        bad(
            f"risk at stop {nsemkt.fmt_inr(risk_inr)} exceeds per-trade limit "
            f"{nsemkt.fmt_inr(per_trade_cap)}"
            + (" (fresh price raised the risk)" if fresh_ltp and fresh_ltp > entry else "")
        )

    # 5. session and entry window
    ss = nsemkt.session_state(now)
    if ss["state"] in ("WEEKEND", "HOLIDAY"):
        bad(f"market closed ({ss['state'].lower()})")
    elif ss["state"] in ("PRE_MARKET", "PRE_OPEN"):
        bad("market has not opened yet")
    elif ss["state"] == "POST_CLOSE":
        bad("market already closed - no new entries today")
    else:
        w0, w1 = rules.get("entry_window", ["09:15", "15:00"])
        if not (_parse_hm(w0) <= now.time() <= _parse_hm(w1)):
            bad(f"outside the entry window {w0}-{w1}")
        flat = _parse_hm(rules.get("flat_by", "15:15"))
        if now.time() >= flat:
            bad(f"past the {rules.get('flat_by')} flat-by time")

    # 6. blocked list
    blocked = {str(t).upper() for t in rules.get("blocked_tickers", [])}
    if ticker in blocked:
        bad(f"{ticker} is on the blocked list")

    # 7. capital / margin (when the caller supplies capital)
    if capital:
        if segment == "FNO":
            margin = order.get("margin_required")
            if margin is None:
                margin = qty * entry * float(rules.get("margin_pct", 15)) / 100.0
            if margin > capital + 1e-6:
                bad(
                    f"F&O margin approx {nsemkt.fmt_inr(margin)} exceeds "
                    f"capital {nsemkt.fmt_inr(capital)}"
                )
        else:
            cost = qty * entry
            if cost > capital + 1e-6:
                bad(f"order value {nsemkt.fmt_inr(cost)} exceeds capital "
                    f"{nsemkt.fmt_inr(capital)}")

    # 8. daily risk cap
    daily_cap = rules.get("daily_loss_limit")
    if daily_cap is None:
        daily_cap = 2.0 * per_trade_cap if per_trade_cap else None
    if daily_cap:
        used = (rules.get("_day_risk", 0.0) or 0.0) + (day_loss or 0.0)
        if used + risk_inr > float(daily_cap) + 1e-6:
            bad(
                f"day risk {nsemkt.fmt_inr(used + risk_inr)} would exceed the "
                f"daily limit {nsemkt.fmt_inr(float(daily_cap))} "
                f"(already used {nsemkt.fmt_inr(used)}, this trade {nsemkt.fmt_inr(risk_inr)})"
            )

    # 9. trade count
    if int(rules.get("_trades_today", 0) or 0) >= int(rules.get("max_trades_per_day", 5)):
        bad(f"already took {rules.get('_trades_today')} trades today "
            f"(max {rules.get('max_trades_per_day')})")

    # 10. duplicate
    if rules.get("_duplicate_ticker"):
        bad(f"{ticker} already passed the gate today - one entry per name per day")

    return reasons, round(risk_inr, 2)


def main() -> None:
    p = argparse.ArgumentParser(
        description="PASS/BLOCK an NSE day-trade ticket before manual broker entry."
    )
    p.add_argument("--order", default=os.path.join(nsemkt.STATE_DIR, "orders.json"))
    p.add_argument("--rules", default=None, help="JSON rules file (merged over defaults)")
    p.add_argument("--fresh-quote", action="store_true",
                   help="re-quote the ticker and size risk from the higher price")
    p.add_argument("--capital", type=float, default=None)
    p.add_argument("--day-loss", type=float, default=0.0,
                   help="realised P&L already lost today in INR")
    p.add_argument("--now", default=None,
                   help="test/backfill clock, IST, e.g. 2026-11-02T09:45")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    order = nsemkt.load_json(args.order)
    if not order:
        print(f"REFUSED: no order at {args.order} (run nse-trader-budget first)",
              file=sys.stderr)
        sys.exit(2)

    rules = dict(DEFAULT_RULES)
    if args.rules:
        extra = nsemkt.load_json(args.rules) or {}
        rules.update(extra)

    now = _now(args)
    day = now.date().isoformat()
    state_path = os.path.join(args.out or nsemkt.STATE_DIR, "risk_state.json")
    state = nsemkt.load_json(state_path) or {}
    if state.get("date") != day:
        state = {"date": day, "verdicts": [], "day_risk_inr": 0.0, "trades_today": 0}

    rules["_day_risk"] = state.get("day_risk_inr", 0.0)
    rules["_trades_today"] = state.get("trades_today", 0)
    ticker = str(order.get("ticker", "")).upper()
    rules["_duplicate_ticker"] = any(
        v.get("verdict") == "PASS" and str(v.get("ticker", "")).upper() == ticker
        for v in state.get("verdicts", [])
    )

    fresh = None
    if args.fresh_quote:
        try:
            fresh = nsemkt.yahoo_quote(ticker)["ltp"]
        except RuntimeError as e:
            print(f"WARNING: fresh quote failed ({e}); using entry price", file=sys.stderr)

    reasons, risk_inr = check(order, rules, now, fresh, args.capital, args.day_loss)
    verdict = "BLOCK" if reasons else "PASS"

    state["verdicts"].append({
        "ts_ist": now.isoformat(timespec="seconds"),
        "ticket": order.get("ticket"),
        "ticker": ticker,
        "verdict": verdict,
        "reasons": reasons,
        "risk_inr": risk_inr,
    })
    if verdict == "PASS":
        state["day_risk_inr"] = round(state.get("day_risk_inr", 0.0) + risk_inr, 2)
        state["trades_today"] = int(state.get("trades_today", 0)) + 1
    nsemkt.save_json(state_path, state)

    if fresh is not None:
        print(f"fresh quote: {ticker} {fresh:.2f}")
    if verdict == "PASS":
        print(f"PASS  {ticker}  qty {order.get('qty')}  risk@stop "
              f"{nsemkt.fmt_inr(risk_inr)}  day risk now "
              f"{nsemkt.fmt_inr(state['day_risk_inr'])}")
        print("  next: nse-trader-broker to print the manual broker ticket")
        sys.exit(0)
    print(f"BLOCK  {ticker}", file=sys.stderr)
    for r in reasons:
        print(f"  - {r}", file=sys.stderr)
    print(f"  day risk stays {nsemkt.fmt_inr(state.get('day_risk_inr', 0.0))}",
          file=sys.stderr)
    sys.exit(3)


if __name__ == "__main__":
    main()
