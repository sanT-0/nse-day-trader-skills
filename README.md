# NSE Day Trader Skills

[![tests](https://github.com/sanT-0/nse-day-trader-skills/actions/workflows/tests.yml/badge.svg)](https://github.com/sanT-0/nse-day-trader-skills/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An open-source, platform-neutral toolkit for **Indian NSE market analysis,
long-side trade planning, risk control, and manual broker order tickets**.

It uses Indian Standard Time, NSE symbols, INR risk, official F&O lot sizes,
configurable broker profiles, and Indian statutory charge estimates.

> **Educational use only.** This is not investment advice, a signal service,
> portfolio management, or an automated trading system. Trading can result in
> loss of capital. Verify every symbol, price, lot size, margin, charge and
> order inside your broker and NSE sources before acting.

## Safety model

- **No broker connection.** The supported workflow never reads broker
  credentials or sends an order.
- **Broker-neutral manual ticket.** The final skill writes portable JSON and
  Markdown after a local risk PASS. Optional profile-specific text is inert.
- **Risk gate is mandatory.** A blocked ticket cannot proceed to the broker
  skill.
- **Long side only.** Cash shares, long futures and long calls/puts are
  supported. Naked/short options are not.
- **No paid API required.** Data comes from public NSE endpoints, Yahoo chart
  JSON and Screener.in. Availability and delay are not guaranteed.

## Skills

| Skill | Purpose |
|---|---|
| `nse-trader` | Router—start here when you do not know which skill to use |
| `nse-trader-market` | NIFTY/BANK NIFTY trend, India VIX, breadth, sectors, FII/DII, and market-health score |
| `nse-trader-scanner` | Scan Nifty 50/100/500 or NSE EQ shares for daily and opening-range setups |
| `nse-trader-flows` | FII/DII cash flow, bulk/block deals and bhavcopy delivery leaders |
| `nse-trader-news` | NSE announcements plus public news headlines for selected tickers |
| `nse-trader-analyst` | Quarterly revenue, profit, EPS and margin analysis with NSE fallback |
| `nse-trader-entry` | Completed 5-minute opening-range or custom-level trigger |
| `nse-trader-exit` | Stop, target, R multiple and flat-by planning |
| `nse-trader-timemachine` | Recent-session replay and bootstrap simulation |
| `nse-trader-budget` | Whole-share/whole-lot sizing with configurable broker charges |
| `nse-trader-risk` | PASS/BLOCK gate for stops, R:R, daily risk, timing, duplicates and capital |
| `nse-trader-broker` | Risk-approved portable manual ticket and local approval/fill log |
| `nse-trader-alerts` | Once-only price, stop, target, opening-bell and flat-by reminders |

## Quick start — no AI application required

```bash
git clone https://github.com/sanT-0/nse-day-trader-skills.git
cd nse-day-trader-skills
python scripts/run.py --list
python scripts/run.py market
```

The Python CLIs are the product core. They use only the standard library and
work without OpenCode, Claude, or another agent. When the dispatcher
runs from the clone, it keeps state under the ignored `.runtime/` directory.

## Agent/application installation

### Generic Agent Skills folder

For applications that discover `SKILL.md` under `~/.agents/skills`:

```bash
python scripts/install.py --target agents
```

For any other app, use its documented skills/instructions directory:

```bash
python scripts/install.py --destination /path/to/your/app/skills
```

Portable ZIPs are available for upload-based applications:

```bash
python scripts/package_skills.py --skill nse-trader-scanner
```

See [docs/platforms.md](docs/platforms.md). An application still needs Python,
filesystem and network permissions to execute live workflows.

### Optional OpenCode adapter

```powershell
python scripts/install.py --target opencode
```

macOS/Linux uses the same command with `python3` if required.

Alternatively, point OpenCode directly at the clone in `opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "skills": ["D:/path/to/nse-day-trader-skills"]
}
```

Using the clone directly makes updates as simple as `git pull`.

### Optional Claude Code adapter

Install compatible skill folders:

```bash
python scripts/install.py --target claude
```

Or copy every `nse-trader*/` directory into `~/.claude/skills/`. The repository
also contains `.claude-plugin` metadata for plugin/marketplace installation.

## Use it

Create a dedicated workspace because runtime state is written under
`./nse-trader/`:

```powershell
mkdir D:\nse-trading
cd D:\nse-trading
```

Advanced users can override that location with `NSE_TRADER_STATE_DIR`. Avoid
running workflows from the repository root because `nse-trader/` there is the
router skill's source directory.

Start with natural language or an explicit skill:

```text
@nse-trader Analyze the Indian market today. Explain the score, breadth,
volatility, sectors, and FII/DII activity. Do not place orders.
```

For a trade plan:

```text
@nse-trader-exit Plan RELIANCE: entry 1166, stop 1158, target 1182.
@nse-trader-budget Capital Rs 100000, max loss Rs 500.
@nse-trader-risk Check the resulting ticket.
@nse-trader-broker Show the portable manual ticket only if risk passed.
```

## Workflow

```text
market → scanner → flows/news → entry → exit → timemachine
        → budget → risk → manual broker ticket → alerts
```

For a daily market review, start with `nse-trader-market`, then use the scanner
only when stock candidates are needed. The overview is not a complete macro,
valuation, or forecasting model. If the market is closed, it reports the last
completed session date.

## Complete skill usage guide

The examples below use the platform-neutral dispatcher from the repository
root:

```bash
python scripts/run.py <command> [options]
```

When invoked this way, state is kept under `.runtime/nse-trader/`. When an
installed agent runs a skill from your own workspace, state defaults to
`./nse-trader/`. Set `NSE_TRADER_STATE_DIR` when you need a different location.

### 1. `nse-trader` — workflow router

**Problem it solves:** You know your trading or analysis goal but do not know
which specialist skill should handle it.

**Use it for:** broad market reviews, stock research, trade planning, position
sizing, risk checks, tickets, and alerts.

**Agent prompt:**

```text
@nse-trader Analyze the Indian market today and tell me which workflow to use.
```

**What it does:** Selects the smallest appropriate workflow and enforces this
order when a full trade is planned:

```text
market → scanner → news → entry → exit → timemachine
       → budget → risk → manual ticket → alerts
```

**What it does not do:** It does not run every skill automatically when only
one specialist is needed, and it never bypasses a risk `BLOCK`.

---

### 2. `nse-trader-market` — overall Indian market condition

**Problem it solves:** NIFTY can rise while most stocks fall, or an index move
can look strong while volatility and sector participation disagree. Looking at
only one index hides that context.

**Measures:**

- NIFTY 50 and BANK NIFTY trend
- India VIX level and direction
- Nifty 50/100 advances, declines, 20DMA/50DMA participation, highs and lows
- nine Nifty sector indices
- FII/FPI and DII cash flow
- data coverage, date alignment, warnings, and confidence

**Agent prompt:**

```text
@nse-trader-market Analyze the Indian market today. Explain the score,
breadth, VIX, sectors, institutional flow, data date, and warnings.
```

**Standalone command:**

```bash
python scripts/run.py market --universe nifty100
```

**Outputs:** `.runtime/nse-trader/market.json` and `market.md`.

**Result:** A transparent `0–100` health score and one of `RISK_ON`,
`POSITIVE`, `NEUTRAL`, `CAUTIOUS`, or `RISK_OFF`. The zone describes observed
conditions; it is not a forecast or an instruction to buy or sell.

---

### 3. `nse-trader-scanner` — find stocks worth reviewing

**Problem it solves:** Manually checking hundreds of NSE charts for the same
setups is slow and inconsistent.

**Finds:** 20-day breakouts, bull flags, 20DMA reclaims, oversold stocks,
oversold bounces, 52-week-high proximity, and intraday opening-range breaks.

**Agent prompt:**

```text
@nse-trader-scanner Scan the Nifty 100 for the strongest daily setups.
```

**Standalone commands:**

```bash
python scripts/run.py scanner --mode daily --universe nifty100 --top 10
python scripts/run.py scanner --mode intraday --universe nifty50 --top 10
```

**Output:** `.runtime/nse-trader/watchlist.json`, including setup labels,
scores, liquidity, pivot levels, and stop hints.

**Limit:** A scanner match is a research candidate, not a trade recommendation.

---

### 4. `nse-trader-flows` — institutional and delivery context

**Problem it solves:** Price movement alone does not show whether FII/DII cash
flows, bulk deals, block deals, and delivery participation support the move.

**Agent prompt:**

```text
@nse-trader-flows Show the latest FII/DII activity, major bulk/block deals,
and delivery leaders.
```

**Standalone command:**

```bash
python scripts/run.py flows --days 5 --top 10
```

**Outputs:** `flows.json` and a locally accumulated FII/DII history.

**Limit:** High delivery can represent accumulation or distribution; it does
not reveal intent by itself.

---

### 5. `nse-trader-news` — detect relevant catalysts

**Problem it solves:** A chart setup can fail when an earnings result,
regulatory filing, dividend, order win, rating change, fund raise, or management
event is missed.

**Agent prompt:**

```text
@nse-trader-news Check new filings and news for RELIANCE, TCS, and HDFCBANK.
```

**Standalone command:**

```bash
python scripts/run.py news --tickers RELIANCE,TCS,HDFCBANK --hours 24
```

**Outputs:** `news.json` and `news_seen.json`. Repeated items are deduplicated.

**Limit:** Keyword tags organize headlines; they do not determine sentiment or
predict the market reaction. Open the original source before relying on it.

---

### 6. `nse-trader-analyst` — understand quarterly results

**Problem it solves:** Earnings headlines often omit whether revenue, profit,
EPS, and margins actually improved compared with the previous quarter or year.

**Agent prompt:**

```text
@nse-trader-analyst Analyze RELIANCE quarterly results, margins, QoQ, YoY,
and trailing-twelve-month performance.
```

**Standalone command:**

```bash
python scripts/run.py analyst --ticker RELIANCE
```

**Outputs:** `facts.json` and `facts.md` with quarterly and TTM figures.

**Fallback:** When the consolidated table cannot be parsed, it lists official
NSE filing links instead of inventing numbers.

---

### 7. `nse-trader-entry` — time a confirmed entry

**Problem it solves:** Entering before a level is confirmed can turn a planned
breakout into an impulsive trade.

**Checks:** The 09:15 opening range or a custom trigger level using completed
5-minute bars and optional relative-volume confirmation.

**Agent prompt:**

```text
@nse-trader-entry Check whether RELIANCE has confirmed an opening-range
breakout today.
```

**Standalone commands:**

```bash
python scripts/run.py entry --ticker RELIANCE --session today --once
python scripts/run.py entry --ticker RELIANCE --level 1450 --min-vol-ratio 1.5
```

**Output:** `entry.json` with `WAITING`, `TRIGGERED`, `EXPIRED`, `NOT_OPEN`, or
`CLOSED`, plus opening-range and trigger details.

**Limit:** It reports a condition; it does not place an entry order.

---

### 8. `nse-trader-exit` — define risk before entry

**Problem it solves:** A trade without a stop, target, flat-by time, and known
reward:risk becomes difficult to manage objectively.

**Agent prompt:**

```text
@nse-trader-exit Plan RELIANCE with entry 1166, stop 1158, and a 2R target.
```

**Standalone command:**

```bash
python scripts/run.py exit --ticker RELIANCE --entry 1166 --stop 1158 --rr 2
```

Stops can come from an explicit price, opening-range midpoint, ATR multiple, or
the documented default. Prices are rounded to the conservative NSE step.

**Output:** `plan.json` with entry, stop, target, R:R, product, and flat-by time.

**Refusals:** Stop at/above entry, target at/below entry, or an unrealistically
tight stop.

---

### 9. `nse-trader-timemachine` — replay the plan

**Problem it solves:** A visually attractive entry/stop/target combination may
have poor behavior when replayed against the stock's recent intraday movement.

**Agent prompt:**

```text
@nse-trader-timemachine Replay the current plan with 10,000 simulations.
```

**Standalone command:**

```bash
python scripts/run.py timemachine --sims 10000 --days 60
```

**Output:** `sim.json` with target-first, stop-first, neither, average R, recent
historical triggers, limitations, and an in-sample verdict.

**Limit:** Bootstrap simulation does not preserve news, market regime, gaps,
slippage, circuit limits, or serial dependence. It is not a forecast.

---

### 10. `nse-trader-budget` — calculate shares or lots

**Problem it solves:** Traders often size by available cash instead of the loss
at the stop, resulting in inconsistent risk.

**Agent prompt:**

```text
@nse-trader-budget I have Rs 100000 and my maximum loss for this trade is
Rs 500. Size the current plan.
```

**Cash command:**

```bash
python scripts/run.py budget --capital 100000 --max-loss 500 --broker generic
```

**Long-option command:**

```bash
python scripts/run.py budget --segment FNO --instrument OPTION \
  --underlying NIFTY --lot-size 65 --capital 100000 --max-loss 2500
```

**Checks:** Max loss including estimated charges, capital, position percentage,
cash buffer, max order value, lot size, futures margin estimate, and long-option
premium.

**Output:** `orders.json` with quantity/lots, charges, max loss, capital need,
and the binding sizing limit.

**Important:** The generic brokerage profile is a visible placeholder. Use a
custom broker profile and verify the contract note.

---

### 11. `nse-trader-risk` — mandatory PASS/BLOCK gate

**Problem it solves:** Even a correctly sized order may violate daily risk,
minimum R:R, time-window, duplicate-trade, blocked-ticker, or capital rules.

**Agent prompt:**

```text
@nse-trader-risk Check whether the current order obeys all my rules.
```

**Standalone command:**

```bash
python scripts/run.py risk --capital 100000 --fresh-quote
```

**Checks:** Valid stop, risk at stop, minimum R:R, entry window, flat-by time,
daily risk, trade count, duplicate ticker, blocked list, and F&O capital.

**Output:** `risk_state.json` and a `PASS` or `BLOCK` verdict with reasons.

**Rule:** A `BLOCK` ends the workflow. Do not modify inputs merely to bypass it.

---

### 12. `nse-trader-broker` — portable manual ticket

**Problem it solves:** A reviewed plan needs a clear, auditable handoff without
giving an agent broker credentials or order-execution authority.

**Prerequisite:** The exact ticket must have a matching risk `PASS`.

**Agent prompt:**

```text
@nse-trader-broker Show the manual ticket for the risk-approved order.
```

**Standalone command:**

```bash
python scripts/run.py ticket --approval "I reviewed and approve this manual ticket"
```

**Outputs:**

- `ticket.json` — broker-neutral schema
- `ticket.md` — human-readable entry and protective exits
- `approvals.jsonl` — exact local approval text
- `fills.jsonl` — fills manually observed by the user

**Limit:** It never contacts a broker. OCO/bracket support and product labels
must be checked in the selected broker.

---

### 13. `nse-trader-alerts` — persistent reminders

**Problem it solves:** Stops, targets, opening time, and intraday flat-by time
are easy to miss while monitoring multiple stocks.

**Agent prompts:**

```text
@nse-trader-alerts Alert me when RELIANCE reaches 1500.
@nse-trader-alerts Add the current plan's stop, target, and 15:15 reminder.
```

**Standalone commands:**

```bash
python scripts/run.py alerts add --ticker RELIANCE --level 1500
python scripts/run.py alerts add --stop
python scripts/run.py alerts add --target
python scripts/run.py alerts add --bell
python scripts/run.py alerts add --ticker RELIANCE --flatby 15:15
python scripts/run.py alerts check --once
python scripts/run.py alerts list
```

**Output:** `alerts.json`. Each alert fires once and is not silently re-armed.

**Limit:** The script does not run by itself in the background and does not send
push notifications. A scheduler or agent must execute `check` periodically.

## Files passed between skills

| File | Created by | Used by |
|---|---|---|
| `market.json` / `market.md` | market | user, router, scanner workflow |
| `watchlist.json` | scanner | news, entry, user |
| `news.json` | news | user and trade review |
| `facts.json` / `facts.md` | analyst | user and earnings review |
| `entry.json` | entry | exit |
| `plan.json` | exit | timemachine, budget, alerts |
| `sim.json` | timemachine | user, budget decision |
| `orders.json` | budget | risk, broker ticket |
| `risk_state.json` | risk | broker ticket, daily risk tracking |
| `ticket.json` / `ticket.md` | broker | manual entry, journals, other apps |
| `alerts.json` | alerts | subsequent alert checks |

## Complete workflow examples

### Daily Indian market review

```text
1. @nse-trader-market Analyze the Indian market today.
2. Explain data date, confidence, score components, breadth, VIX, and sectors.
3. @nse-trader-scanner Scan only if stock candidates are needed.
4. @nse-trader-flows Show detailed bulk/block and delivery activity if needed.
5. @nse-trader-news Check catalysts only for selected candidates.
```

Standalone:

```bash
python scripts/run.py market
python scripts/run.py scanner --mode daily --universe nifty100 --top 10
python scripts/run.py flows --days 5 --top 10
python scripts/run.py news --tickers RELIANCE,TCS --hours 24
```

### Cash-equity trade plan

```bash
python scripts/run.py entry --ticker RELIANCE --session today --once
python scripts/run.py exit --ticker RELIANCE --entry 1166 --stop 1158 --rr 2
python scripts/run.py timemachine --sims 10000 --days 60
python scripts/run.py budget --capital 100000 --max-loss 500
python scripts/run.py risk --capital 100000 --fresh-quote
python scripts/run.py ticket --approval "Reviewed for manual entry"
python scripts/run.py alerts add --stop
python scripts/run.py alerts add --target
python scripts/run.py alerts add --ticker RELIANCE --flatby 15:15
```

Stop immediately if entry is not triggered, the plan is refused, simulation is
unacceptable to you, one share cannot fit the risk limit, or risk returns
`BLOCK`.

### Long-option plan

```bash
python scripts/run.py exit --ticker NIFTY26NOV26000CE \
  --entry 180 --stop 150 --target 240 --segment FNO --instrument OPTION
python scripts/run.py budget --segment FNO --instrument OPTION \
  --underlying NIFTY --lot-size 65 --capital 100000 --max-loss 2500
python scripts/run.py risk --capital 100000
python scripts/run.py ticket --approval "Reviewed long-option manual ticket"
```

Verify the exact live contract symbol, expiry, strike, option type, lot size,
premium, liquidity, product, and broker margin before manual entry. Short/naked
options remain outside this toolkit's scope. The Time Machine requires usable
5-minute bars for the exact contract and may be unavailable for option symbols
on the public data source.

## India/NSE conventions

| Convention | Value |
|---|---|
| Time zone | IST (UTC+05:30), fixed offset—no `tzdata` dependency |
| Pre-open | 09:00 IST |
| Continuous market | 09:15–15:30 IST |
| New-entry cutoff | 15:00 IST |
| Conservative intraday flat-by | 15:15 IST |
| Currency | INR |
| Default price step | Conservative Rs 0.05; verify the current instrument tick in your broker |
| Holidays | Bundled 2026 fallback plus cached official NSE holiday refresh |
| F&O lots | Current NSE `fo_mktlots.csv`, cached locally |

## F&O scope

Supported:

- long futures
- long calls and puts using the exact contract symbol
- official underlying lot-size lookup, with manual override
- futures margin estimate
- long-option premium requirement
- generic/custom broker charge estimate

Not supported:

- naked/short options
- multi-leg options payoff or portfolio-margin modeling
- expiry/assignment automation
- automatic rollovers
- broker execution

Your broker's live margin display and contract note are authoritative.

## Broker-neutral charge profiles

The default profile uses a visible Rs 20-per-executed-order placeholder; it is
not guaranteed conservative for every broker.
Use a custom JSON profile for any Indian broker; Groww is retained as one
optional built-in profile captured on **2026-11-01**. The model also estimates
STT, stamp duty, exchange transaction charges, SEBI turnover charge, IPFT and
GST. Delivery DP charges and unusual levies can differ. See
[docs/broker-profiles.md](docs/broker-profiles.md); the contract note wins.

The manual handoff follows the app-neutral
[`ticket.json` schema](docs/ticket-schema.md), allowing a GUI, spreadsheet,
journal, or agent to consume the same reviewed plan without broker credentials.

## Data sources

| Data | Source |
|---|---|
| Equity master | NSE `EQUITY_L.csv` |
| Index universes | NSE Nifty 50/100/500 constituent CSVs (bundled snapshot) |
| F&O lots | NSE `fo_mktlots.csv` |
| Holidays | NSE holiday-master API plus offline fallback |
| Announcements | NSE corporate-announcements API |
| FII/DII | NSE `fiidiiTradeReact` |
| Bulk/block deals | NSE capital-market large-deal snapshot |
| Delivery percentage | NSE full bhavcopy |
| OHLCV/quotes | Yahoo chart JSON (`.NS`), potentially delayed |
| Fundamentals | Screener.in consolidated table, with NSE filing fallback |

External schemas and access policies can change. Every skill reports missing
sources instead of fabricating data.

## Development and tests

Python 3.9+ with no third-party runtime dependency.

```bash
python scripts/sync_shared.py --check
python scripts/verify_skills.py
python -m unittest discover -s tests -v
```

Network tests are opt-in and excluded from CI:

```bash
LIVE=1 python -m unittest tests.test_live_sources -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Updating

```bash
git pull
python scripts/install.py --target agents --force
```

When an agent uses this repository directly as a recursive skill source, only
`git pull` is needed.

## License

MIT licensed.
