#!/usr/bin/env python3
"""nse-trader-budget: size an NSE position to a capital base and max loss.

Reads ./nse-trader/plan.json (entry/stop/target), finds the largest whole-share
(CASH) or whole-lot (FNO) size that fits every limit *including estimated
broker/statutory charges*,
then writes ./nse-trader/orders.json for the risk gate and the ticket printer.

Nothing is placed. A stop too far away for the max loss is a refusal, not a
smaller order.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import nsemkt


def _largest_fitting(feasible, hi: int) -> int:
    """Largest n in [1, hi] with feasible(n), else 0. Assumes monotonicity."""
    if hi < 1:
        return 0
    if not feasible(1):
        return 0
    lo, best = 1, 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if feasible(mid):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def size_cash(plan: dict, args) -> dict:
    ticker = plan["ticker"]
    entry, stop = float(plan["entry"]), float(plan["stop"])
    risk = entry - stop
    if risk <= 0:
        raise ValueError("plan stop must be below entry")

    product = plan.get("product", "MIS")
    capital = args.capital
    usable = capital - args.cash_buffer

    caps = {
        "max_loss": 10**9,
        "max_order": 10**9,
        "position_pct": int(math.floor(usable * args.max_position_pct / 100.0 / entry)),
        "capital": int(math.floor(usable / entry)),
    }
    if args.max_order:
        caps["max_order"] = int(math.floor(args.max_order / entry))

    hi = max(0, min(v for k, v in caps.items() if k != "max_loss"))

    def feasible(qty: int) -> bool:
        if qty <= 0 or qty > hi:
            return False
        rt = nsemkt.round_trip_charges(
            "CASH", qty, entry, stop, product,
            broker=args.broker, broker_profile=args.broker_profile_data,
        )["total"]
        return qty * risk + rt <= args.max_loss + 1e-6

    qty = _largest_fitting(feasible, hi)
    if qty < 1:
        one_rt = nsemkt.round_trip_charges(
            "CASH", 1, entry, stop, product,
            broker=args.broker, broker_profile=args.broker_profile_data,
        )["total"]
        need = risk + one_rt
        raise ValueError(
            f"1 share risks {nsemkt.fmt_inr(need)} at the stop incl. charges "
            f"(max loss {nsemkt.fmt_inr(args.max_loss)}); stop is too far or "
            "capital too small"
        )

    binding = "max_loss"
    for k, v in sorted(caps.items(), key=lambda kv: kv[1]):
        if v == qty:
            binding = k
            break

    cost = qty * entry
    rt = nsemkt.round_trip_charges(
        "CASH", qty, entry, stop, product,
        broker=args.broker, broker_profile=args.broker_profile_data,
    )
    gross = qty * risk
    return {
        "segment": "CASH",
        "qty": qty,
        "lots": None,
        "lot_size": 1,
        "cost": round(cost, 2),
        "charges": rt,
        "gross_loss_at_stop": round(gross, 2),
        "max_loss_at_stop": round(gross + rt["total"], 2),
        "decided_by": binding,
        "margin_required": None,
    }


def size_fno(plan: dict, args) -> dict:
    ticker = plan["ticker"]
    entry, stop = float(plan["entry"]), float(plan["stop"])
    risk = entry - stop
    if risk <= 0:
        raise ValueError("plan stop must be below entry")

    instrument = (args.instrument or plan.get("instrument") or "FUTURE").upper()
    if instrument not in ("FUTURE", "OPTION"):
        raise ValueError("FNO requires --instrument FUTURE or OPTION")
    lot = args.lot_size
    if not lot:
        lots_map = nsemkt.fo_lots()
        lookup = (args.underlying or ticker).upper()
        lot = lots_map.get(lookup)
        if not lot:
            raise ValueError(
                f"no F&O lot size found for {lookup}; pass --underlying or --lot-size "
                "(lot sizes change per expiry)"
            )
    lot = int(lot)
    usable = args.capital - args.cash_buffer
    if instrument == "OPTION":
        # Long options: capital required is the premium paid. Short/naked option
        # risk is non-linear and intentionally unsupported by this long-side tool.
        margin_per_lot = lot * entry
        charge_product = "OPT"
    else:
        margin_per_lot = lot * entry * args.margin_pct / 100.0
        charge_product = "FUT"

    caps = {"max_loss": 10**9, "capital": int(math.floor(usable / margin_per_lot))}
    if args.max_order:
        caps["max_order"] = int(math.floor(args.max_order / (lot * entry)))
    if args.lots:
        if args.lots < 1:
            raise ValueError("--lots must be positive")
        caps["requested_lots"] = args.lots
    hi = max(0, min(caps.values()))

    def feasible(n: int) -> bool:
        if n <= 0 or n > hi:
            return False
        qty = n * lot
        rt = nsemkt.round_trip_charges(
            "FNO", qty, entry, stop, charge_product,
            broker=args.broker, broker_profile=args.broker_profile_data,
        )["total"]
        risk_ok = n * risk * lot + rt <= args.max_loss + 1e-6
        if instrument == "OPTION":
            buy_charges = nsemkt.broker_charges(
                "FNO", "BUY", qty, entry, "OPT",
                broker=args.broker, broker_profile=args.broker_profile_data,
            )["total"]
            capital_ok = qty * entry + buy_charges <= usable + 1e-6
        else:
            capital_ok = n * margin_per_lot <= usable + 1e-6
        return risk_ok and capital_ok

    n = _largest_fitting(feasible, hi)
    if n < 1:
        rt1 = nsemkt.round_trip_charges(
            "FNO", lot, entry, stop, charge_product,
            broker=args.broker, broker_profile=args.broker_profile_data,
        )["total"]
        requirement = margin_per_lot
        requirement_name = "premium" if instrument == "OPTION" else "estimated margin"
        raise ValueError(
            f"1 lot ({lot}) risks {nsemkt.fmt_inr(risk * lot + rt1)} at the stop "
            f"incl. charges (max loss {nsemkt.fmt_inr(args.max_loss)}); "
            f"{requirement_name} is {nsemkt.fmt_inr(requirement)}; "
            "stop too far or capital too small"
        )

    qty = n * lot
    rt = nsemkt.round_trip_charges(
        "FNO", qty, entry, stop, charge_product,
        broker=args.broker, broker_profile=args.broker_profile_data,
    )
    gross = qty * risk
    capital_required = n * margin_per_lot
    if instrument == "OPTION":
        capital_required += nsemkt.broker_charges(
            "FNO", "BUY", qty, entry, "OPT",
            broker=args.broker, broker_profile=args.broker_profile_data,
        )["total"]
    binding = "max_loss"
    for k, v in sorted(caps.items(), key=lambda kv: kv[1]):
        if v == n:
            binding = k
            break
    return {
        "segment": "FNO",
        "instrument": instrument,
        "qty": qty,
        "lots": n,
        "lot_size": lot,
        "cost": round(qty * entry, 2),
        "charges": rt,
        "gross_loss_at_stop": round(gross, 2),
        "max_loss_at_stop": round(gross + rt["total"], 2),
        "decided_by": binding,
        "margin_required": round(capital_required, 2),
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Size an NSE trade to capital and max loss (no order placed)."
    )
    p.add_argument("--plan", default=os.path.join(nsemkt.STATE_DIR, "plan.json"))
    p.add_argument("--capital", type=float, required=True, help="trading capital in INR")
    p.add_argument("--max-loss", type=float, required=True,
                   help="max loss for this trade in INR, charges included")
    p.add_argument("--max-order", type=float, default=None,
                   help="cap on order value in INR (optional)")
    p.add_argument("--max-position-pct", type=float, default=25.0,
                   help="max %% of capital in one position (default 25)")
    p.add_argument("--cash-buffer", type=float, default=0.0,
                   help="capital to keep unused (default 0)")
    p.add_argument("--segment", choices=["CASH", "FNO"], default=None,
                   help="defaults to the plan's segment")
    p.add_argument("--instrument", choices=["FUTURE", "OPTION"], default=None,
                   help="F&O instrument; defaults to the plan (or FUTURE)")
    p.add_argument("--underlying", default=None,
                   help="underlying symbol for lot lookup when ticker is a contract")
    p.add_argument("--lots", type=int, default=None,
                   help="force a lot count (FNO); skipped if it breaches limits")
    p.add_argument("--lot-size", type=int, default=None,
                   help="override the F&O lot size")
    p.add_argument("--margin-pct", type=float, default=15.0,
                   help="F&O margin as %% of notional (est., default 15)")
    p.add_argument("--broker", choices=["generic", "groww"], default="generic",
                   help="brokerage profile (default generic flat Rs 20/order)")
    p.add_argument("--broker-profile", default=None,
                   help="custom brokerage JSON; overrides the selected profile")
    p.add_argument("--out", default=None)
    args = p.parse_args()
    try:
        args.broker_profile_data = nsemkt.load_broker_profile(args.broker_profile)
        resolved_profile = nsemkt.resolve_broker_profile(
            args.broker, args.broker_profile_data
        )
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)

    plan = nsemkt.load_json(args.plan)
    if not plan:
        print(f"REFUSED: no plan at {args.plan} (run nse-trader-exit first)", file=sys.stderr)
        sys.exit(2)
    seg = (args.segment or plan.get("segment") or "CASH").upper()
    if args.capital <= 0 or args.max_loss <= 0:
        print("REFUSED: capital and max-loss must be positive", file=sys.stderr)
        sys.exit(2)

    try:
        sized = size_cash(plan, args) if seg == "CASH" else size_fno(plan, args)
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)

    order = {
        "ticket": plan.get("ticket", "ticket"),
        "plan_ticket": plan.get("ticket"),
        "ticker": plan["ticker"],
        "segment": sized["segment"],
        "instrument": sized.get("instrument", plan.get("instrument", "EQUITY")),
        "product": plan.get("product", "MIS"),
        "side": "BUY",
        "qty": sized["qty"],
        "lots": sized["lots"],
        "lot_size": sized["lot_size"],
        "entry": float(plan["entry"]),
        "stop": float(plan["stop"]),
        "target": float(plan["target"]),
        "risk_per_share": round(float(plan["entry"]) - float(plan["stop"]), 2),
        "charges": sized["charges"],
        "broker": args.broker,
        "broker_profile": resolved_profile["name"],
        "broker_profile_rules": resolved_profile,
        "broker_profile_file": args.broker_profile,
        "gross_loss_at_stop": sized["gross_loss_at_stop"],
        "max_loss_at_stop": sized["max_loss_at_stop"],
        "cost": sized["cost"],
        "margin_required": sized["margin_required"],
        "decided_by": sized["decided_by"],
        "capital": args.capital,
        "max_loss": args.max_loss,
        "flat_by": plan.get("flat_by", "15:15"),
        "created_ist": nsemkt.now_ist().isoformat(timespec="seconds"),
        "status": "AWAITING_RISK_CHECK",
    }

    out_dir = args.out or nsemkt.STATE_DIR
    path = nsemkt.save_json(os.path.join(out_dir, "orders.json"), order)

    qty_desc = f"{order['qty']} shares"
    if order["lots"]:
        qty_desc = f"{order['lots']} lot(s) x {order['lot_size']} = {order['qty']} qty"
    print(f"ORDER  {order['ticker']}  BUY {qty_desc}  @ {order['entry']:.2f}  "
          f"stop {order['stop']:.2f}  target {order['target']:.2f}")
    print(f"  value at entry : {nsemkt.fmt_inr(order['cost'])}")
    print(f"  round-trip chg : {nsemkt.fmt_inr(order['charges']['total'])}")
    print(f"  charge profile : {order['broker_profile']}")
    print(f"  max loss@stop  : {nsemkt.fmt_inr(order['max_loss_at_stop'])} "
          f"(limit {nsemkt.fmt_inr(order['max_loss'])})")
    if order["margin_required"] is not None:
        label = "premium needed" if order.get("instrument") == "OPTION" else "margin approx"
        print(f"  {label:<14}: {nsemkt.fmt_inr(order['margin_required'])}")
    print(f"  decided by     : {order['decided_by']}")
    print(f"  saved          : {path}")
    print("  next           : run nse-trader-risk to PASS/BLOCK, then nse-trader-broker")


if __name__ == "__main__":
    main()
