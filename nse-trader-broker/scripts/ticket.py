#!/usr/bin/env python3
"""Render a risk-approved NSE order as a broker-neutral manual ticket.

This script never imports a broker SDK, reads credentials or calls a broker.
It writes portable JSON plus a human ticket. When explicitly requested for the
Groww profile, the Markdown can include an inert SDK illustration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import nsemkt


def append_jsonl(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")


def passed_risk(order: dict, risk_path: str) -> tuple[bool, str]:
    state = nsemkt.load_json(risk_path) or {}
    ticket = order.get("ticket")
    matches = [v for v in state.get("verdicts", [])
               if v.get("ticket") == ticket and v.get("verdict") == "PASS"]
    if not matches:
        return False, f"no PASS for ticket {ticket!r} in {risk_path}"
    return True, matches[-1].get("ts_ist", "unknown time")


def reference_id(order: dict, suffix: str) -> str:
    raw = f"{order.get('ticket')}|{suffix}"
    return f"nt-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"


def groww_sdk_example(order: dict) -> str:
    symbol = str(order["ticker"]).upper()
    qty = int(order["qty"])
    entry = float(order["entry"])
    stop = float(order["stop"])
    target = float(order["target"])
    segment = str(order.get("segment", "CASH")).upper()
    product = str(order.get("product", "MIS")).upper()
    segment_const = "groww.SEGMENT_FNO" if segment == "FNO" else "groww.SEGMENT_CASH"
    # Official smart-order docs require NRML for F&O OCO and allow MIS for CASH.
    product_const = "groww.PRODUCT_NRML" if segment == "FNO" else (
        "groww.PRODUCT_MIS" if product == "MIS" else "groww.PRODUCT_CNC"
    )
    entry_ref = reference_id(order, "entry")
    oco_ref = reference_id(order, "oco")
    entry_only = f'''# OPTIONAL MANUAL EXAMPLE — THIS FILE HAS NOT EXECUTED IT.
# Verified against Groww Python SDK Orders + Smart Orders docs on 2026-11-01.
# Install/subscription/token are your responsibility. Never paste a token into chat.
from growwapi import GrowwAPI
import os

token = os.environ["GROWW_API_AUTH_TOKEN"]
groww = GrowwAPI(token)

# STEP 1: entry only. Confirm symbol/qty/prices in Groww before running.
entry_response = groww.place_order(
    trading_symbol={symbol!r},
    quantity={qty},
    validity=groww.VALIDITY_DAY,
    exchange=groww.EXCHANGE_NSE,
    segment={segment_const},
    product={product_const},
    order_type=groww.ORDER_TYPE_LIMIT,
    transaction_type=groww.TRANSACTION_TYPE_BUY,
    price={entry:.2f},
    order_reference_id={entry_ref!r},
)
print(entry_response)
'''
    if segment == "CASH" and product != "MIS":
        return entry_only + '''

# Groww's current Smart Orders documentation lists CASH OCO support for MIS,
# not CNC. This skill therefore does not generate a CNC OCO example. Protect
# the filled delivery position manually in Groww using currently supported
# order types, and verify that only one exit can execute.
'''
    return entry_only + f'''

# STOP HERE. Verify the entry is fully filled before protecting it.
# STEP 2: OCO exits an EXISTING position. One exit cancels the other.
oco_response = groww.create_smart_order(
    smart_order_type=groww.SMART_ORDER_TYPE_OCO,
    reference_id={oco_ref!r},
    segment={segment_const},
    trading_symbol={symbol!r},
    quantity={qty},
    product_type={product_const},
    exchange=groww.EXCHANGE_NSE,
    duration=groww.VALIDITY_DAY,
    net_position_quantity={qty},
    transaction_type=groww.TRANSACTION_TYPE_SELL,
    target={{
        "trigger_price": "{target:.2f}",
        "order_type": groww.ORDER_TYPE_LIMIT,
        "price": "{target:.2f}",
    }},
    stop_loss={{
        "trigger_price": "{stop:.2f}",
        "order_type": groww.ORDER_TYPE_STOP_LOSS_MARKET,
        "price": None,
    }},
)
print(oco_response)
'''


def portable_ticket(order: dict, risk_pass_time: str, status: str,
                    broker: str) -> dict:
    qty = int(order["qty"])
    entry, stop, target = (float(order[k]) for k in ("entry", "stop", "target"))
    return {
        "schema_version": "1.0",
        "ticket": order.get("ticket"),
        "status": status,
        "risk_passed_ist": risk_pass_time,
        "broker": broker,
        "exchange": "NSE",
        "segment": order.get("segment", "CASH"),
        "instrument": order.get("instrument", "EQUITY"),
        "product": order.get("product", "MIS"),
        "entry_order": {
            "transaction": "BUY", "order_type": "LIMIT",
            "symbol": order["ticker"], "quantity": qty, "price": entry,
            "validity": "DAY",
        },
        "protective_exit": {
            "activate_only_after_full_entry_fill": True,
            "oco_preferred": True,
            "stop": {
                "transaction": "SELL", "order_type": "SL-M",
                "quantity": qty, "trigger_price": stop,
            },
            "target": {
                "transaction": "SELL", "order_type": "LIMIT",
                "quantity": qty, "price": target,
            },
        },
        "estimated_charges": order.get("charges"),
        "max_loss_at_stop": order.get("max_loss_at_stop"),
        "flat_by_ist": order.get("flat_by", "15:15"),
        "execution": "MANUAL_ONLY",
    }


def markdown_ticket(order: dict, risk_pass_time: str, status: str,
                    broker: str) -> str:
    ticker = order["ticker"]
    qty = int(order["qty"])
    entry, stop, target = (float(order[k]) for k in ("entry", "stop", "target"))
    charges = float((order.get("charges") or {}).get("total") or 0)
    max_loss = float(order.get("max_loss_at_stop") or 0)
    broker_label = broker if broker != "generic" else "your broker"
    optional = ""
    if broker.lower() == "groww":
        optional = f"""

## Optional Groww SDK illustration

```python
{groww_sdk_example(order).rstrip()}
```

Re-check <https://groww.in/trade-api/docs/python-sdk/orders> and Smart Orders
before using the example; API contracts and supported products can change.
"""
    return f"""# Manual NSE broker ticket — {order.get('ticket')}

**Status:** {status}

**Risk PASS:** {risk_pass_time} IST

**This skill did not contact {broker_label} or place an order.**

| Field | Value |
|---|---|
| Broker profile | {broker} |
| Exchange / segment | NSE / {order.get('segment', 'CASH')} |
| Instrument | {order.get('instrument', 'EQUITY')} |
| Product | {order.get('product', 'MIS')} |
| Entry | BUY {qty} {ticker} @ Rs {entry:.2f} LIMIT |
| Stop after fill | SELL {qty} @ trigger Rs {stop:.2f} SL-M |
| Target after fill | SELL {qty} @ Rs {target:.2f} LIMIT |
| Charge profile | {order.get('broker_profile', 'generic-flat-20')} |
| Est. round-trip charges | Rs {charges:.2f} |
| Max loss at stop | Rs {max_loss:.2f} |
| Flat by | {order.get('flat_by', '15:15')} IST |

## Manual broker sequence

1. Open the exact NSE instrument in {broker_label}; for F&O verify expiry,
   strike, option type and lot size.
2. Enter the BUY limit ticket and re-check quantity, product and price.
3. Only after the entry is **fully filled**, use your broker's OCO/bracket
   feature for the target and SL-M stop when available. Otherwise manage the
   exits manually and ensure two separate exits cannot both execute.
4. For this intraday plan, close and cancel remaining exits by {order.get('flat_by', '15:15')} IST
   regardless of the product label used by the broker.
{optional}
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Print a broker-neutral manual ticket for a risk-approved NSE order.")
    p.add_argument("--order", default=os.path.join(nsemkt.STATE_DIR, "orders.json"))
    p.add_argument("--risk-state", default=None,
                   help="risk_state.json; default is beside the order file")
    p.add_argument("--broker", default=None,
                   help="broker label/profile; defaults to the order (generic)")
    p.add_argument("--approval", default=None,
                   help="your exact approval phrase; logged locally, never sent")
    p.add_argument("--fill", action="store_true",
                   help="record a fill you manually observed in your broker")
    p.add_argument("--price", type=float, default=None, help="manual fill price")
    p.add_argument("--qty", type=int, default=None, help="manual filled quantity")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    order = nsemkt.load_json(args.order)
    if not order:
        print(f"REFUSED: no order at {args.order}", file=sys.stderr)
        sys.exit(2)
    required = ("ticket", "ticker", "qty", "entry", "stop", "target")
    if any(order.get(k) in (None, "") for k in required):
        print("REFUSED: malformed order; ticket/ticker/qty/entry/stop/target required", file=sys.stderr)
        sys.exit(2)

    risk_path = args.risk_state or os.path.join(os.path.dirname(os.path.abspath(args.order)), "risk_state.json")
    ok, risk_info = passed_risk(order, risk_path)
    if not ok:
        print(f"REFUSED: {risk_info}; run nse-trader-risk first", file=sys.stderr)
        sys.exit(2)

    out_dir = args.out or nsemkt.STATE_DIR
    status = "APPROVED_FOR_MANUAL_ENTRY" if args.approval else "AWAITING_APPROVAL"
    default_broker = order.get("broker") or "generic"
    if default_broker == "generic" and order.get("broker_profile") not in (
        None, "generic-flat-20"
    ):
        default_broker = order.get("broker_profile")
    broker = str(args.broker or default_broker).strip().lower()
    md = markdown_ticket(order, risk_info, status, broker)
    portable = portable_ticket(order, risk_info, status, broker)
    ticket_path = os.path.join(out_dir, "ticket.md")
    json_path = os.path.join(out_dir, "ticket.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(ticket_path, "w", encoding="utf-8") as f:
        f.write(md)
    nsemkt.save_json(json_path, portable)

    event = {
        "ts_ist": nsemkt.now_ist().isoformat(timespec="seconds"),
        "ticket": order["ticket"],
        "ticker": order["ticker"],
        "broker": broker,
        "status": status,
        "approval": args.approval,
    }
    if args.approval:
        append_jsonl(os.path.join(out_dir, "approvals.jsonl"), event)

    if args.fill:
        if not args.approval:
            print("REFUSED: --fill requires --approval so the decision is logged", file=sys.stderr)
            sys.exit(2)
        if not args.price or not args.qty or args.price <= 0 or args.qty <= 0:
            print("REFUSED: --fill requires positive --price and --qty", file=sys.stderr)
            sys.exit(2)
        append_jsonl(os.path.join(out_dir, "fills.jsonl"), {
            **event,
            "status": "MANUAL_FILL_RECORDED",
            "fill_price": args.price,
            "fill_qty": args.qty,
            "source": f"user-observed {broker} fill",
        })

    print(md.split("## Optional Groww SDK illustration", 1)[0].rstrip())
    print(f"\nStatus: {status}")
    if args.fill:
        print(f"Manual fill recorded: {args.qty} @ Rs {args.price:.2f}")
    print(f"Human ticket: {ticket_path}")
    print(f"Portable JSON ticket: {json_path}")
    print("NO ORDER WAS SENT TO ANY BROKER.")


if __name__ == "__main__":
    main()
