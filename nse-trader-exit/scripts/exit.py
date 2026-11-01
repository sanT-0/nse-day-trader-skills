#!/usr/bin/env python3
"""nse-trader-exit: plan the stop and target for an NSE trade before entry.

Pure planning - no orders, no network unless ATR is needed. Writes
./nse-trader/plan.json (or --out DIR/plan.json) for budget/risk/timemachine.

Stop precedence: --stop > opening-range midpoint > ATR14 x mult > 0.8% default.
All prices round to the NSE 0.05 tick (stop down, target up).
"""

from __future__ import annotations

import argparse
import os
import sys

import nsemkt


def build_plan(args) -> dict:
    ticker = args.ticker.strip().upper()
    entry = nsemkt.round_tick(args.entry)
    if entry <= 0:
        raise ValueError("entry price must be positive")

    warnings: list[str] = []

    if args.from_entry and not args.or_low and not args.or_high:
        saved = nsemkt.load_json(nsemkt.state_path("entry.json")) or {}
        if saved.get("ticker", "").upper() == ticker:
            args.or_low = saved.get("or_low") or args.or_low
            args.or_high = saved.get("or_high") or args.or_high
            if saved.get("status") == "TRIGGERED":
                warnings.append(f"entry.json shows TRIGGERED at {saved.get('trigger_price')}")
        else:
            warnings.append("no entry.json for this ticker - using other stop sources")

    if args.stop is not None:
        stop = nsemkt.round_tick(args.stop, "down")
        basis = "explicit stop"
    elif args.or_low and args.or_high:
        if not (args.or_low < entry < args.or_high) and args.or_high <= args.or_low:
            raise ValueError("or-low must be below or-high")
        stop = nsemkt.round_tick((args.or_low + args.or_high) / 2.0, "down")
        basis = "opening-range midpoint"
    elif args.atr_mult:
        atr = nsemkt.atr_daily(ticker)
        if not atr:
            raise ValueError(f"no ATR data for {ticker}")
        stop = nsemkt.round_tick(entry - args.atr_mult * atr, "down")
        basis = f"ATR14 x {args.atr_mult}"
    else:
        stop = nsemkt.round_tick(entry * 0.992, "down")
        basis = "0.8% below entry (default)"

    if args.target is not None:
        target = nsemkt.round_tick(args.target, "up")
    else:
        rr = args.rr if args.rr else 2.0
        target = nsemkt.round_tick(entry + rr * (entry - stop), "up")

    risk = entry - stop
    if stop <= 0 or stop >= entry:
        raise ValueError(f"stop {stop} must be below entry {entry}")
    if target <= entry:
        raise ValueError(f"target {target} must be above entry {entry}")
    min_risk = max(2 * nsemkt.TICK, 0.0015 * entry)
    if risk < min_risk:
        raise ValueError(
            f"stop too tight: {risk:.2f} per share < {min_risk:.2f} "
            "(spread/whipsaw risk)"
        )
    rr_actual = (target - entry) / risk
    if rr_actual < 0.5:
        raise ValueError(f"reward:risk {rr_actual:.2f} is below 0.5")

    segment = args.segment.upper()
    instrument = args.instrument.upper()
    if segment == "CASH" and instrument != "EQUITY":
        raise ValueError("CASH segment requires --instrument EQUITY")
    if segment == "FNO" and instrument == "EQUITY":
        raise ValueError("FNO segment requires --instrument FUTURE or OPTION")
    product = (args.product or ("NRML" if segment == "FNO" else "MIS")).upper()
    if segment == "FNO" and product == "CNC":
        raise ValueError("CNC is not an F&O product; use NRML")
    flat_by = "15:30" if product == "CNC" else "15:15"
    ss = nsemkt.session_state()
    if ss["state"] in ("WEEKEND", "HOLIDAY", "POST_CLOSE"):
        warnings.append(f"market is {ss['state'].lower()}; plan applies to the next session")

    plan = {
        "ticket": f"{nsemkt.today_ist().strftime('%Y%m%d')}-{ticker}-1",
        "ticker": ticker,
        "segment": segment,
        "instrument": instrument,
        "product": product,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "rr": round(rr_actual, 2),
        "risk_per_share": round(risk, 2),
        "stop_basis": basis,
        "flat_by": flat_by,
        "created_ist": nsemkt.now_ist().isoformat(timespec="seconds"),
        "valid": True,
        "reason": None,
        "warnings": warnings,
    }
    return plan


def main() -> None:
    p = argparse.ArgumentParser(
        description="Plan an NSE trade's stop and target (no order placed)."
    )
    p.add_argument("--ticker", required=True, help="NSE symbol, e.g. RELIANCE")
    p.add_argument("--entry", type=float, required=True, help="planned entry price (INR)")
    p.add_argument("--stop", type=float, default=None, help="explicit stop price")
    p.add_argument("--or-low", type=float, default=None, help="opening-range low")
    p.add_argument("--or-high", type=float, default=None, help="opening-range high")
    p.add_argument("--atr-mult", type=float, default=None,
                   help="ATR14 multiple for the stop (skip to use default)")
    p.add_argument("--rr", type=float, default=2.0, help="reward:risk for the target (default 2)")
    p.add_argument("--target", type=float, default=None, help="explicit target price")
    p.add_argument("--product", default=None, choices=["MIS", "CNC", "NRML"],
                   help="default MIS for cash, NRML for F&O")
    p.add_argument("--segment", default="CASH", choices=["CASH", "FNO"])
    p.add_argument("--instrument", default=None,
                   choices=["EQUITY", "FUTURE", "OPTION"],
                   help="default EQUITY for CASH, FUTURE for FNO")
    p.add_argument("--from-entry", action="store_true",
                   help="read opening range/trigger from nse-trader/entry.json")
    p.add_argument("--out", default=None, help="output directory (default nse-trader)")
    args = p.parse_args()
    if args.instrument is None:
        args.instrument = "EQUITY" if args.segment == "CASH" else "FUTURE"

    try:
        plan = build_plan(args)
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)

    out_dir = args.out or nsemkt.STATE_DIR
    path = nsemkt.save_json(os.path.join(out_dir, "plan.json"), plan)

    print(f"PLAN  {plan['ticker']}  entry {plan['entry']:.2f}  stop {plan['stop']:.2f}  "
          f"target {plan['target']:.2f}  RR {plan['rr']:.1f}")
    print(f"  stop basis   : {plan['stop_basis']}")
    print(f"  risk/share   : {nsemkt.fmt_inr(plan['risk_per_share'])}")
    print(f"  flat by      : {plan['flat_by']} ({plan['product']})")
    for w in plan["warnings"]:
        print(f"  note         : {w}")
    print(f"  saved        : {path}")


if __name__ == "__main__":
    main()
