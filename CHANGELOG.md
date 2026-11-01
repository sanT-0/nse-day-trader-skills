# Changelog

All notable changes follow a simplified Keep a Changelog format.

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
