# Changelog

All notable changes follow a simplified Keep a Changelog format.

## [0.4.0] - 2026-11-02

### Changed

- FII/DII freshness is now judged in **completed NSE trading sessions**, not
  calendar days: Friday figures on Monday, or on the Tuesday after a Monday
  holiday, are the latest available published session (`FRESH`,
  `sessions_behind: 0`) and are no longer reported as stale by calendar age
- freshness classification is now strictly local (bundled calendar + cache,
  zero network on the classification path); calendar coverage is reported
  per year (`calendar_years`, `calendar_verified_years`), and the one-time
  official holiday-master refresh is bounded (8s timeout, single retry,
  week-long cache TTL)
- FII/DII metadata now also carries `latest_completed_session`,
  `sessions_behind`, `freshness_status` (`FRESH`/`DELAYED`/`STALE`/`UNKNOWN`)
  and `calendar_verified`; a missing or unverified holiday calendar reports
  `UNKNOWN` freshness instead of a silent assumption
- `nse-trader-market` report lines show the human session date
  (`Friday, 30 Oct 2026`), freshness, calendar age, sessions behind and
  "Live intraday flow: No" beside every FII/DII figure; score-component
  detail includes sessions behind
- `nse-trader-flows` CLI prints the freshness summary line
- skill instructions (`nse-trader`, `nse-trader-market`, `nse-trader-flows`,
  `nse-trader-entry`) require surfacing sessions-behind/freshness at the
  entry planner, warning on `DELAYED`/`STALE`/unverified data, and keeping
  end-of-day institutional figures separate from price/volume intraday
  signals

- FII/DII numbers can no longer appear without their session/date context:
  every value now carries `data_date`, `market_session_date`, `retrieved_at`,
  `data_status` (`LIVE`, `CURRENT_SESSION`, `PREVIOUS_SESSION`, `END_OF_DAY`,
  `STALE`, `UNKNOWN`), `is_live` (always false — daily published aggregates are
  not live intraday flow) and `is_previous_session`
- `nse-trader-market` excludes `STALE`/`UNKNOWN` FII/DII from the health score
  with a warning, and the report/JSON/CLI state the session date and status
  beside every FII/DII figure plus the "context, not live intraday flow"
  disclaimer
- `nse-trader-flows` prints the data session and status with the FII/DII table
  and stores a structured `fii_dii_meta` block in `flows.json`
- skill instructions (`nse-trader`, `nse-trader-market`, `nse-trader-flows`,
  `nse-trader-entry`) now require showing FII/DII session dates and forbid
  presenting previous-session/end-of-day figures as live intraday activity or
  entry triggers

### Added

- shared FII/DII freshness helpers in `shared/nsemkt.py`
  (`fii_dii_freshness`, `fii_dii_dataset`, `parse_nse_flow_date`,
  `last_trading_day`) with tests for previous-session, after-close, missing
  date, stale and intraday-entry cases

## [0.3.0] - 2026-11-01

### Added

- `nse-trader-market` as the primary “Analyze the Indian market today” workflow
- transparent 0–100 score across NIFTY trend, breadth, India VIX, BANK NIFTY,
  sector participation, and FII/DII cash flow
- provisional-live versus last-completed-session labels
- breadth coverage, component coverage, confidence, source warnings, JSON and
  Markdown reports
- index-symbol support in the shared Yahoo adapter and offline scoring tests

## [0.2.0] - 2026-11-01

### Changed

- made the default workflow broker-neutral instead of Groww-specific
- added configurable brokerage JSON profiles and a conservative generic default
- changed the broker handoff to portable `ticket.json` plus human Markdown
- retained Groww only as an optional built-in charge/SDK-illustration profile
- made standalone Python CLIs the primary platform-neutral interface

### Added

- platform-neutral command dispatcher (`scripts/run.py`)
- generic `~/.agents/skills` and custom-destination installation paths
- deterministic ZIP packaging with SHA-256 sums
- machine-readable `skills-manifest.json`
- platform and custom-broker documentation

## [0.1.0] - 2026-11-01

### Added

- `nse-trader` workflow router
- eleven standalone NSE analysis and trade-planning skills
- Nifty 50/100/500 scanner universes
- official NSE holiday cache with a bundled 2026 fallback
- NSE F&O lot-size lookup
- versioned Groww cash, futures and options charge estimates
- cash, futures and long-option position sizing
- mandatory PASS/BLOCK risk gate and manual-only Groww ticket
- stdlib-only installer, shared-module synchronizer and repository verifier
- deterministic offline tests plus opt-in live NSE/Yahoo smoke tests
- OpenCode and Claude Code installation paths
