#!/usr/bin/env python3
"""Read Indian quarterly fundamentals without inventing missing numbers.

Primary source: Screener.in's public consolidated quarterly table. If that
page is unavailable or cannot be parsed, the script falls back to links for
official NSE result filings and explicitly leaves numeric fields empty.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import os
import re
import sys
import urllib.parse

import nsemkt


class QuarterlyParser(HTMLParser):
    """Collect rows from the first table inside section#quarters."""

    def __init__(self) -> None:
        super().__init__()
        self.section_depth = 0
        self.in_quarters = False
        self.in_table = False
        self.in_cell = False
        self.cell_tag = ""
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []
        self.company_parts: list[str] = []
        self.in_h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.in_h1 = True
        if tag == "section" and a.get("id") == "quarters":
            self.in_quarters = True
            self.section_depth = 1
            return
        if self.in_quarters and tag == "section":
            self.section_depth += 1
        if self.in_quarters and tag == "table" and not self.in_table:
            self.in_table = True
        if self.in_table and tag == "tr":
            self.row = []
        if self.in_table and tag in ("th", "td"):
            self.in_cell = True
            self.cell_tag = tag
            self.cell_parts = []

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False
        if self.in_cell and tag == self.cell_tag:
            text = html.unescape(" ".join(self.cell_parts))
            text = re.sub(r"\s+", " ", text).replace(" +", "").strip()
            self.row.append(text)
            self.in_cell = False
        if self.in_table and tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = []
        if self.in_table and tag == "table":
            self.in_table = False
        if self.in_quarters and tag == "section":
            self.section_depth -= 1
            if self.section_depth <= 0:
                self.in_quarters = False

    def handle_data(self, data):
        if self.in_h1:
            self.company_parts.append(data.strip())
        if self.in_cell:
            stripped = data.strip()
            if stripped:
                self.cell_parts.append(stripped)


def number(value: str) -> float | None:
    raw = value.replace(",", "").replace("%", "").strip()
    if raw in ("", "-", "--"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def change(current: float | None, old: float | None) -> float | None:
    if current is None or old in (None, 0):
        return None
    return round((current / old - 1.0) * 100.0, 2)


def parse_screener(ticker: str) -> tuple[str, list[dict], dict]:
    url = f"https://www.screener.in/company/{urllib.parse.quote(ticker)}/consolidated/"
    page = nsemkt.http_get(url, timeout=35)
    parser = QuarterlyParser()
    parser.feed(page)
    if len(parser.rows) < 3:
        raise ValueError("quarterly-results table not found")

    header = parser.rows[0]
    periods = header[1:] if header and header[0] == "" else header
    # Some HTML parsers omit the blank first TH. Make period alignment explicit.
    if periods and periods[0].lower().startswith(("sales", "expenses")):
        raise ValueError("could not identify quarterly periods")
    rows: dict[str, list[float | None]] = {}
    for row in parser.rows[1:]:
        if len(row) < 2:
            continue
        label = row[0].strip().lower()
        rows[label] = [number(v) for v in row[1:]]
    sales = rows.get("sales")
    profit = rows.get("net profit")
    eps = rows.get("eps in rs")
    opm = rows.get("opm %")
    op_profit = rows.get("operating profit")
    if not sales or not profit or not periods:
        raise ValueError("Sales/Net Profit rows were not parseable")

    length = min(len(periods), len(sales), len(profit))
    quarters: list[dict] = []
    for i in range(length):
        revenue = sales[i]
        net_profit = profit[i]
        net_margin = (net_profit / revenue * 100.0) if revenue not in (None, 0) and net_profit is not None else None
        q = {
            "period": periods[i],
            "revenue_cr": revenue,
            "net_profit_cr": net_profit,
            "eps_rs": eps[i] if eps and i < len(eps) else None,
            "op_margin_pct": opm[i] if opm and i < len(opm) else None,
            "net_margin_pct": round(net_margin, 2) if net_margin is not None else None,
            "revenue_qoq_pct": change(revenue, sales[i - 1]) if i >= 1 else None,
            "revenue_yoy_pct": change(revenue, sales[i - 4]) if i >= 4 else None,
            "profit_qoq_pct": change(net_profit, profit[i - 1]) if i >= 1 else None,
            "profit_yoy_pct": change(net_profit, profit[i - 4]) if i >= 4 else None,
        }
        quarters.append(q)

    last4 = quarters[-4:]
    revs = [q["revenue_cr"] for q in last4]
    profits = [q["net_profit_cr"] for q in last4]
    epss = [q["eps_rs"] for q in last4]
    ttm_revenue = sum(x for x in revs if x is not None) if all(x is not None for x in revs) else None
    ttm_profit = sum(x for x in profits if x is not None) if all(x is not None for x in profits) else None
    ttm_eps = sum(x for x in epss if x is not None) if all(x is not None for x in epss) else None
    op_values = op_profit[-4:] if op_profit and len(op_profit) >= 4 else []
    ttm_op_profit = sum(x for x in op_values if x is not None) if len(op_values) == 4 and all(x is not None for x in op_values) else None
    ttm = {
        "revenue_cr": round(ttm_revenue, 2) if ttm_revenue is not None else None,
        "net_profit_cr": round(ttm_profit, 2) if ttm_profit is not None else None,
        "eps_rs": round(ttm_eps, 2) if ttm_eps is not None else None,
        "op_margin_pct": round(ttm_op_profit / ttm_revenue * 100.0, 2)
            if ttm_op_profit is not None and ttm_revenue else None,
        "net_margin_pct": round(ttm_profit / ttm_revenue * 100.0, 2)
            if ttm_profit is not None and ttm_revenue else None,
    }
    company = re.sub(r"\s+", " ", " ".join(parser.company_parts)).strip() or ticker
    return company, quarters, ttm


def fallback_filings(ticker: str) -> list[dict]:
    url = (
        "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol="
        + urllib.parse.quote(ticker)
    )
    data = nsemkt.http_json(url, timeout=40)
    filings: list[dict] = []
    for row in data if isinstance(data, list) else []:
        if str(row.get("symbol", "")).upper() != ticker:
            continue
        text = f"{row.get('desc', '')} {row.get('attchmntText', '')}".lower()
        if not any(k in text for k in ("financial result", "quarterly result", "audited result", "unaudited result")):
            continue
        filings.append({
            "date": row.get("an_dt") or row.get("sort_date"),
            "title": row.get("attchmntText") or row.get("desc"),
            "url": row.get("attchmntFile"),
        })
        if len(filings) >= 12:
            break
    return filings


def fmt_metric(value, suffix="") -> str:
    return "N/A" if value is None else f"{value:,.2f}{suffix}"


def report_markdown(facts: dict) -> str:
    lines = [f"# {facts['ticker']} quarterly facts", "", f"Source: {facts['source']}", ""]
    if facts["quarters"]:
        q = facts["quarters"][-1]
        lines += [
            f"## Latest quarter — {q['period']}", "",
            "| Metric | Value | QoQ | YoY |", "|---|---:|---:|---:|",
            f"| Revenue | Rs {fmt_metric(q['revenue_cr'])} cr | {fmt_metric(q['revenue_qoq_pct'], '%')} | {fmt_metric(q['revenue_yoy_pct'], '%')} |",
            f"| Net profit | Rs {fmt_metric(q['net_profit_cr'])} cr | {fmt_metric(q['profit_qoq_pct'], '%')} | {fmt_metric(q['profit_yoy_pct'], '%')} |",
            f"| EPS | Rs {fmt_metric(q['eps_rs'])} | — | — |",
            f"| Operating margin | {fmt_metric(q['op_margin_pct'], '%')} | — | — |",
            f"| Net margin | {fmt_metric(q['net_margin_pct'], '%')} | — | — |",
            "", "## TTM", "",
            f"Revenue Rs {fmt_metric(facts['ttm'].get('revenue_cr'))} cr; "
            f"net profit Rs {fmt_metric(facts['ttm'].get('net_profit_cr'))} cr; "
            f"EPS Rs {fmt_metric(facts['ttm'].get('eps_rs'))}.",
        ]
    else:
        lines += [
            "Numeric quarterly data could not be parsed. Official NSE filing links are listed below;",
            "open the PDF or paste its table before drawing a conclusion.", "",
        ]
        for f in facts.get("filings", []):
            lines.append(f"- {f.get('date')}: [{f.get('title')}]({f.get('url')})")
    lines += ["", "Figures are source data, not an investment recommendation."]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description="Read quarterly facts for an NSE company.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--screener", action="store_true",
                   help="use Screener.in (already the default; retained for explicit workflows)")
    p.add_argument("--out", default=None)
    args = p.parse_args()
    ticker = args.ticker.strip().upper()
    if not ticker or not re.fullmatch(r"[A-Z0-9&-]{1,30}", ticker):
        print("REFUSED: invalid NSE ticker", file=sys.stderr)
        sys.exit(2)

    notes: list[str] = []
    filings: list[dict] = []
    try:
        company, quarters, ttm = parse_screener(ticker)
        source = "Screener.in consolidated quarterly results (Rs crore)"
    except Exception as e:
        notes.append(f"Screener parse unavailable: {e}")
        quarters, ttm, company = [], {}, ticker
        try:
            filings = fallback_filings(ticker)
            source = "NSE corporate-announcement links (numeric parse unavailable)"
        except Exception as fallback_error:
            notes.append(f"NSE fallback unavailable: {fallback_error}")
            source = "unavailable"

    facts = {
        "ticker": ticker,
        "name": company,
        "source": source,
        "generated_ist": nsemkt.now_ist().isoformat(timespec="seconds"),
        "quarters": quarters,
        "ttm": ttm,
        "filings": filings,
        "notes": notes,
    }
    out_dir = args.out or nsemkt.STATE_DIR
    json_path = nsemkt.save_json(os.path.join(out_dir, "facts.json"), facts)
    md = report_markdown(facts)
    md_path = os.path.join(out_dir, "facts.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md.rstrip())
    print(f"\nparsed quarters: {len(quarters)}")
    print(f"saved: {json_path}")
    print(f"saved: {md_path}")


if __name__ == "__main__":
    main()
