---
name: nse-trader-entry
description: Entry Timer for NSE. Reads free 5-minute NSE bars, builds the 09:15 opening range and reports WAITING, TRIGGERED, EXPIRED, NOT_OPEN or CLOSED when a completed bar closes above the range or your level with optional volume confirmation. Use when the user says "tell me when to enter", "watch RELIANCE", "has it broken out", "opening range breakout", "entry signal", "entry kab le", or after nse-trader-scanner and nse-trader-news.
---

# nse-trader-entry

Times a **long-side** NSE entry using completed 5-minute bars. By default it
builds the 09:15–09:30 IST opening range and triggers only when a completed bar
closes above its high with at least 1.2× the preceding ten bars' average
volume. It reports status; it does not place an order.

## Run it

Check today's RELIANCE opening-range breakout:

```bash
python scripts/entry.py --ticker RELIANCE --session today --once
```

Check a scanner pivot instead:

```bash
python scripts/entry.py --ticker RELIANCE --level 1452.50 --min-vol-ratio 1.5
```

Replay the last completed session (useful after hours):

```bash
python scripts/entry.py --ticker RELIANCE --session last
```

Set `--min-vol-ratio 0` to disable volume confirmation. Change the range with
`--or-minutes 30` (must be a 5-minute multiple).

## Status contract

| Status | Meaning |
|---|---|
| `WAITING` | session is open; no qualifying completed bar yet |
| `TRIGGERED` | first qualifying bar closed above the level |
| `EXPIRED` | no trigger before the 15:00 new-entry cutoff |
| `NOT_OPEN` | today's market/session data does not exist yet |
| `CLOSED` | replayed session ended without a qualifying trigger |

The script explicitly labels historical analysis as `CLOSED`; it never calls a
past bar a live signal. Yahoo NSE data can be delayed—confirm the bar and price
inside your broker or an exchange-grade feed.

## Rules

- NSE normal session: 09:15–15:30 IST
- default opening range: first 15 minutes
- only a **completed** 5-minute close can trigger
- default minimum volume: 1.2× prior-ten-bar average
- no new entry after 15:00; MIS positions should be flat by 15:15
- long side only

## Files

| File | What |
|---|---|
| `nse-trader/entry.json` | status, OR levels, trigger, price, volume ratio |

After `TRIGGERED`, run `nse-trader-exit` immediately to define the stop and
target **before** sizing the trade.

Educational tooling only, not financial advice.
