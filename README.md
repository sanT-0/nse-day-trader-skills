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
python scripts/run.py scanner --mode daily --universe nifty100 --top 10
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
@nse-trader Analyze the Indian market today. Scan Nifty 100, summarize the
setups and FII/DII activity, and create a watchlist. Do not place orders.
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
scanner → flows/news → entry → exit → timemachine
        → budget → risk → manual broker ticket → alerts
```

For a daily market review, `scanner + flows` is the baseline. This is a setup
and institutional-flow view—not a complete macro, breadth or valuation model.
If the market is closed, the skills report the last completed session date.

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
