---
name: nse-trader-flows
description: Indian Institutional Flow Monitor. Reads official NSE FII/DII cash activity, bulk deals, block deals and bhavcopy delivery percentages, with client names and turnover leaders. Use when the user says "FII DII data", "who is buying Indian stocks", "bulk deals today", "block deals", "institutional flow", "delivery percentage", "FII buying hai?", or wants an India-appropriate alternative to the US politician-trade tracker.
---

# nse-trader-flows

Shows what the Indian market actually discloses at exchange level:

- FII/FPI and DII aggregate cash-market buying, selling and net flow
- NSE bulk deals and block deals, including published client names
- top-turnover `EQ` shares and their delivery percentage from the latest
  official security bhavcopy

No API key is required. It does not infer a hidden buyer or recommend copying
any participant.

## Run it

```bash
python scripts/flows.py --days 5 --top 10
```

`--days` controls the FII/DII dates shown. NSE's live endpoint normally exposes
the latest date, so the skill accumulates earlier snapshots locally as you run
it each day. It says so explicitly when fewer dates are available.

## Reading the output

- **FII/DII net** is market-wide Rs crore flow, not a stock signal.
- **Bulk deal** generally reflects a large percentage/quantity transaction
  reported by the exchange; the published client name may be an intermediary.
- **Block deal** occurred in a designated block window and does not by itself
  reveal intent.
- **Delivery %** can distinguish delivery-oriented volume from intraday churn,
  but high delivery can represent either accumulation or distribution.
- Cross-check unusual rows against the NSE source and company announcements.

## Honest replacement for the Pelosi tracker

India does **not** provide a US STOCK-Act-style, standardized near-real-time
feed of MPs' personal stock transactions that this toolkit can reliably parse.
This skill therefore replaces `trader-pelosi` with official institutional and
large-deal data. It does not claim to track Indian politicians' portfolios.

## Files

| File | What |
|---|---|
| `nse-trader/flows.json` | current FII/DII, bulk/block and delivery snapshot |
| `nse-trader/flows_history.json` | locally accumulated FII/DII dates |

Sources are official NSE endpoints and archive bhavcopy files. Endpoint
availability and schemas can change; missing sections are reported, never
fabricated. Educational tooling only, not financial advice.
