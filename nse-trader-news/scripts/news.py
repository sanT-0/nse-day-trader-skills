#!/usr/bin/env python3
"""Fetch new NSE filings and public news headlines for a watchlist.

Primary source is NSE corporate announcements. Google News RSS supplements it
with media headlines. Items are tagged, hashed and remembered so repeated runs
do not spam the same headline. No API key is used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

import nsemkt


def parse_nse_time(value: str) -> dt.datetime | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(value, fmt).replace(tzinfo=nsemkt.IST)
        except (TypeError, ValueError):
            pass
    return None


def parse_rss_time(value: str) -> dt.datetime | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(nsemkt.IST)
    except (TypeError, ValueError):
        return None


def tags_for(text: str) -> list[str]:
    t = text.lower()
    rules = [
        ("results", ("financial result", "quarter", "earnings", "profit", "revenue", "results")),
        ("board-meeting", ("board meeting", "meeting of board")),
        ("dividend", ("dividend", "record date", "ex-date")),
        ("order-win", ("order win", "order received", "contract", "letter of award", "work order")),
        ("regulatory", ("sebi", "rbi", "regulatory", "show cause", "penalty", "investigation")),
        ("rating", ("credit rating", "rating revision", "crisil", "icra", "care ratings")),
        ("fund-raise", ("fund rais", "qip", "rights issue", "preferential", "debenture", "borrow")),
        ("management", ("resignation", "appointment", "ceo", "cfo", "director", "management")),
    ]
    found = [name for name, needles in rules if any(n in t for n in needles)]
    return found or ["other"]


def item_id(title: str, url: str) -> str:
    return hashlib.sha1((title.strip() + "\n" + url.strip()).encode("utf-8")).hexdigest()


def company_names(tickers: list[str]) -> dict[str, str]:
    try:
        master = nsemkt.nse_symbols()
        mapping = {r["symbol"].upper(): r["name"] for r in master}
    except Exception:
        mapping = {}
    return {t: mapping.get(t, t) for t in tickers}


def nse_items(ticker: str, cutoff: dt.datetime) -> list[dict]:
    url = (
        "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol="
        + urllib.parse.quote(ticker)
    )
    data = nsemkt.http_json(url, timeout=40)
    out: list[dict] = []
    for row in data if isinstance(data, list) else []:
        if str(row.get("symbol", "")).upper() != ticker:
            continue
        when = parse_nse_time(row.get("an_dt") or row.get("sort_date"))
        if not when or when < cutoff:
            continue
        title = html.unescape(str(row.get("attchmntText") or row.get("desc") or "NSE announcement")).strip()
        url_ = str(row.get("attchmntFile") or "")
        desc = str(row.get("desc") or "")
        out.append({
            "id": item_id(title, url_),
            "ts_ist": when.isoformat(timespec="seconds"),
            "ticker": ticker,
            "source": "NSE filing",
            "title": title,
            "url": url_,
            "tags": tags_for(title + " " + desc),
            "summary": desc,
        })
    return out


def rss_items(ticker: str, company: str, cutoff: dt.datetime) -> list[dict]:
    query = f'"{company}" NSE stock'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"
    })
    xml = nsemkt.http_get(url, timeout=30)
    root = ET.fromstring(xml)
    out: list[dict] = []
    for node in root.findall(".//item"):
        title = html.unescape((node.findtext("title") or "").strip())
        link = (node.findtext("link") or "").strip()
        when = parse_rss_time(node.findtext("pubDate") or "")
        if not title or not when or when < cutoff:
            continue
        source_node = node.find("source")
        source = source_node.text.strip() if source_node is not None and source_node.text else "Google News"
        clean = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
        out.append({
            "id": item_id(title, link),
            "ts_ist": when.isoformat(timespec="seconds"),
            "ticker": ticker,
            "source": source,
            "title": clean or title,
            "url": link,
            "tags": tags_for(title),
            "summary": "Public headline via Google News RSS; open the source before relying on it.",
        })
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch new NSE filings and news for selected tickers.")
    p.add_argument("--tickers", required=True, help="comma-separated NSE symbols")
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--since", action="store_true",
                   help="only after the previous successful run (otherwise --hours)")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    tickers = list(dict.fromkeys(t.strip().upper() for t in args.tickers.split(",") if t.strip()))
    if not tickers or args.hours <= 0:
        print("REFUSED: provide tickers and a positive --hours", file=sys.stderr)
        sys.exit(2)

    out_dir = args.out or nsemkt.STATE_DIR
    seen_path = os.path.join(out_dir, "news_seen.json")
    seen_state = nsemkt.load_json(seen_path) or {"ids": [], "last_run_ist": None}
    seen = set(seen_state.get("ids") or [])
    now = nsemkt.now_ist()
    cutoff = now - dt.timedelta(hours=args.hours)
    if args.since and seen_state.get("last_run_ist"):
        try:
            cutoff = max(cutoff, dt.datetime.fromisoformat(seen_state["last_run_ist"]))
        except ValueError:
            pass

    names = company_names(tickers)
    collected: list[dict] = []
    errors: list[str] = []
    for ticker in tickers:
        try:
            collected.extend(nse_items(ticker, cutoff))
        except Exception as e:
            errors.append(f"{ticker} NSE: {e}")
        try:
            collected.extend(rss_items(ticker, names[ticker], cutoff))
        except Exception as e:
            errors.append(f"{ticker} RSS: {e}")

    # De-duplicate both against history and within this response.
    fresh: list[dict] = []
    run_ids: set[str] = set()
    for item in collected:
        if item["id"] in seen or item["id"] in run_ids:
            continue
        run_ids.add(item["id"])
        fresh.append(item)
    fresh.sort(key=lambda x: x["ts_ist"], reverse=True)

    payload = {
        "generated_ist": now.isoformat(timespec="seconds"),
        "tickers": tickers,
        "cutoff_ist": cutoff.isoformat(timespec="seconds"),
        "items": fresh,
        "errors": errors,
        "data_note": "NSE filings are primary; media headlines require opening the original source.",
    }
    result_path = nsemkt.save_json(os.path.join(out_dir, "news.json"), payload)
    all_ids = (list(seen) + list(run_ids))[-5000:]
    nsemkt.save_json(seen_path, {
        "last_run_ist": now.isoformat(timespec="seconds"),
        "ids": all_ids,
    })

    print(f"NEWS  {', '.join(tickers)}  {len(fresh)} new item(s)")
    for item in fresh[:25]:
        print(f"  {item['ts_ist'][5:16].replace('T', ' ')}  {item['ticker']:<12} "
              f"[{','.join(item['tags'])}] {item['title'][:110]}")
    if errors:
        print(f"WARNING: {len(errors)} source error(s); details are in news.json")
    print(f"saved: {result_path}")


if __name__ == "__main__":
    main()
