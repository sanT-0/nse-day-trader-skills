#!/usr/bin/env python3
"""Snapshot official NSE institutional-flow and large-deal data.

This is the India-appropriate replacement for a US politician-disclosure
tracker: FII/DII cash flows, NSE bulk/block deals and delivery percentages from
the official bhavcopy. It does not attribute beneficial ownership beyond the
client names NSE publishes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import sys

import nsemkt


def as_float(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fii_dii() -> list[dict]:
    data = nsemkt.http_json("https://www.nseindia.com/api/fiidiiTradeReact")
    out = []
    for row in data if isinstance(data, list) else []:
        out.append({
            "date": row.get("date"),
            "category": row.get("category"),
            "buy_cr": as_float(row.get("buyValue")),
            "sell_cr": as_float(row.get("sellValue")),
            "net_cr": as_float(row.get("netValue")),
        })
    return out


def large_deals(top: int) -> tuple[list[dict], list[dict], str | None]:
    url = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
    data = nsemkt.http_json(url)

    def convert(rows):
        out = []
        for row in rows or []:
            out.append({
                "date": row.get("date"),
                "symbol": row.get("symbol"),
                "company": row.get("name"),
                "client": row.get("clientName"),
                "side": row.get("buySell"),
                "quantity": int(as_float(row.get("qty")) or 0),
                "price": as_float(row.get("watp")),
                "remarks": row.get("remarks"),
            })
        out.sort(key=lambda x: x["quantity"], reverse=True)
        return out[:top]

    return convert(data.get("BULK_DEALS_DATA")), convert(data.get("BLOCK_DEALS_DATA")), data.get("as_on_date")


def latest_bhavcopy(top: int) -> tuple[str | None, list[dict], list[str]]:
    notes: list[str] = []
    day = nsemkt.today_ist()
    attempts = 0
    while attempts < 12:
        if nsemkt.is_trading_day(day):
            token = day.strftime("%d%m%Y")
            url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{token}.csv"
            try:
                text = nsemkt.http_get(url, timeout=25, retries=0)
                rows = []
                for raw in csv.DictReader(io.StringIO(text)):
                    row = {str(k).strip(): (v.strip() if isinstance(v, str) else v)
                           for k, v in raw.items()}
                    if row.get("SERIES") != "EQ":
                        continue
                    turnover_lakh = as_float(row.get("TURNOVER_LACS")) or 0.0
                    rows.append({
                        "symbol": row.get("SYMBOL"),
                        "close": as_float(row.get("CLOSE_PRICE")),
                        "change_pct": (
                            round(((as_float(row.get("CLOSE_PRICE")) or 0) /
                                   (as_float(row.get("PREV_CLOSE")) or 1) - 1) * 100, 2)
                        ),
                        "volume": int(as_float(row.get("TTL_TRD_QNTY")) or 0),
                        "turnover_cr": round(turnover_lakh / 100.0, 2),
                        "delivery_qty": int(as_float(row.get("DELIV_QTY")) or 0),
                        "delivery_pct": as_float(row.get("DELIV_PER")),
                    })
                rows.sort(key=lambda x: x["turnover_cr"], reverse=True)
                return day.isoformat(), rows[:top], notes
            except Exception as e:
                notes.append(f"bhavcopy {day.isoformat()} unavailable: {e}")
        day -= dt.timedelta(days=1)
        attempts += 1
    return None, [], notes


def merge_history(path: str, current: list[dict], days: int) -> list[dict]:
    previous = nsemkt.load_json(path) or []
    merged: dict[tuple[str, str], dict] = {}
    for row in previous + current:
        key = (str(row.get("date")), str(row.get("category")))
        merged[key] = row
    rows = list(merged.values())
    rows.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    # The live endpoint exposes the latest observation only; this local history
    # accumulates across runs. Keep a bounded archive and report available rows.
    nsemkt.save_json(path, rows[:120])
    unique_dates: list[str] = []
    for row in rows:
        d = str(row.get("date"))
        if d not in unique_dates:
            unique_dates.append(d)
    allowed = set(unique_dates[:days])
    return [r for r in rows if str(r.get("date")) in allowed]


def main() -> None:
    p = argparse.ArgumentParser(description="NSE FII/DII, bulk/block and delivery-flow snapshot.")
    p.add_argument("--days", type=int, default=5,
                   help="locally accumulated FII/DII dates to show (default 5)")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    if args.days < 1 or args.top < 1:
        print("REFUSED: --days and --top must be positive", file=sys.stderr)
        sys.exit(2)

    out_dir = args.out or nsemkt.STATE_DIR
    notes: list[str] = []
    try:
        latest_flows = fii_dii()
    except Exception as e:
        latest_flows = []
        notes.append(f"FII/DII endpoint unavailable: {e}")
    flows = merge_history(os.path.join(out_dir, "flows_history.json"), latest_flows, args.days)

    try:
        bulk, block, deal_date = large_deals(args.top)
    except Exception as e:
        bulk, block, deal_date = [], [], None
        notes.append(f"large-deal endpoint unavailable: {e}")

    bhav_date, delivery, bhav_notes = latest_bhavcopy(args.top)
    notes.extend(bhav_notes[-3:])
    if len({r.get("date") for r in flows}) < args.days:
        notes.append(
            "NSE's live FII/DII endpoint exposes the latest date; --days history "
            "accumulates locally on repeated runs."
        )

    payload = {
        "generated_ist": nsemkt.now_ist().isoformat(timespec="seconds"),
        "fii_dii": flows,
        "block_deals": block,
        "bulk_deals": bulk,
        "deal_date": deal_date,
        "delivery_date": bhav_date,
        "delivery_leaders": delivery,
        "notes": notes,
        "source": "Official NSE APIs and NSE bhavcopy",
    }
    path = nsemkt.save_json(os.path.join(out_dir, "flows.json"), payload)

    print("FII / DII CASH FLOW (Rs crore)")
    for row in flows:
        print(f"  {row.get('date',''):<12} {row.get('category',''):<8} "
              f"buy {row.get('buy_cr') or 0:>10,.2f}  sell {row.get('sell_cr') or 0:>10,.2f}  "
              f"net {row.get('net_cr') or 0:>+10,.2f}")
    print(f"\nBULK DEALS ({deal_date or 'unavailable'})")
    for row in bulk[:args.top]:
        print(f"  {row['symbol']:<14} {row['side'] or '':<4} {row['quantity']:>10,} @ "
              f"{row['price'] or 0:>9,.2f}  {str(row['client'])[:45]}")
    print(f"\nBLOCK DEALS ({deal_date or 'unavailable'})")
    for row in block[:args.top]:
        print(f"  {row['symbol']:<14} {row['side'] or '':<4} {row['quantity']:>10,} @ "
              f"{row['price'] or 0:>9,.2f}  {str(row['client'])[:45]}")
    print(f"\nDELIVERY / TURNOVER LEADERS ({bhav_date or 'unavailable'})")
    for row in delivery[:args.top]:
        dp = "N/A" if row["delivery_pct"] is None else f"{row['delivery_pct']:.1f}%"
        print(f"  {row['symbol']:<14} turnover {row['turnover_cr']:>9,.2f} cr  "
              f"delivery {dp:>7}  chg {row['change_pct']:>+6.2f}%")
    for note in notes:
        print(f"NOTE: {note}")
    print(f"saved: {path}")


if __name__ == "__main__":
    main()
