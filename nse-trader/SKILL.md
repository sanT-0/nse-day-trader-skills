---
name: nse-trader
description: Router for the portable NSE Day Trader skill pack. Use when a user asks to analyze the Indian market today, find NSE trades, build a broker-neutral workflow, check FII/DII activity, plan an Indian stock or F&O trade, or is unsure which nse-trader-* skill to use. It routes through scanner, flows, news, entry, exit, simulation, sizing, risk, manual broker ticket and alerts without placing orders.
---

# NSE Trader

Route an Indian-market request to the smallest safe workflow. All times are
IST, prices are INR, primary exchange data is NSE, and every broker handoff is manual.
Never imply that any script places an order.

## First determine the intent

| User goal | Load and use |
|---|---|
| “Analyze the Indian market today” | `nse-trader-scanner`, then `nse-trader-flows` |
| Find stocks to watch | `nse-trader-scanner` |
| Explain a move or check catalysts | `nse-trader-news` |
| Review company results | `nse-trader-analyst` |
| Check FII/DII or large deals | `nse-trader-flows` |
| Time an opening-range entry | `nse-trader-entry` |
| Set stop and target | `nse-trader-exit` |
| Replay or simulate a plan | `nse-trader-timemachine` |
| Calculate shares or lots | `nse-trader-budget` |
| Decide whether a ticket breaks limits | `nse-trader-risk` |
| Prepare a broker-neutral ticket | `nse-trader-broker` only after risk PASS |
| Watch stop, target, open or flat-by | `nse-trader-alerts` |

Load the selected skill by exact ID before following its workflow.

## Daily-market workflow

For “analyze the market today”:

1. Load `nse-trader-scanner` and scan Nifty 100 daily setups. During market
   hours, optionally run its intraday opening-range scan.
2. Load `nse-trader-flows` and report FII/DII net cash flow, major bulk/block
   deals, and delivery/turnover leaders.
3. Explain breadth cautiously: the scanner is a setup scan, not a complete
   advance/decline or macro-regime model.
4. If the user wants specific candidates, load `nse-trader-news` for only the
   selected tickers.
5. Present a watchlist—not buy/sell commands.

If the market is closed, state the exact data/session date and call the result
a last-completed-session review rather than live analysis.

## Trade-planning workflow

```text
scanner → news → entry → exit → timemachine → budget → risk
        → manual broker ticket → alerts
```

Do not skip `nse-trader-exit`, `nse-trader-budget`, or `nse-trader-risk` before
the broker ticket. A BLOCK verdict ends the workflow; do not work around it.

## F&O boundary

- supported: long futures and long calls/puts
- use official NSE lot-size data and the exact contract symbol
- long-option capital is full premium plus estimated charges
- unsupported: naked/short options, multi-leg payoff modeling and automatic
  broker execution
- the selected broker’s displayed margin and contract note are authoritative

## Workspace

Run from a dedicated folder, for example `D:\nse-trading`. Skills write state
under `./nse-trader/` (or `NSE_TRADER_STATE_DIR`). Do not run them inside this
skill pack or an unrelated source repository.

## Data and safety language

- Yahoo chart data can be delayed; confirm prices in your broker/exchange view.
- NSE endpoints and Screener.in can change or be temporarily unavailable.
- State the source date and any source failures.
- Never request or display broker credentials.
- The default ticket is portable JSON/Markdown. Optional broker-specific text
  is illustrative and is never executed by this pack.
- Educational tooling only; not financial advice.
