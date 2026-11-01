# Contributing

Contributions are welcome for correctness, tests, documentation and Indian
market coverage. Do not add automated order placement, credential collection,
scraped paywall content or unbounded short-option strategies.

## Development setup

Python 3.9+ and the standard library are sufficient.

```bash
python scripts/sync_shared.py --check
python scripts/verify_skills.py
python -m unittest discover -s tests -v
```

Network smoke tests are opt-in:

```bash
LIVE=1 python -m unittest tests.test_live_sources -v
```

PowerShell:

```powershell
$env:LIVE = "1"
python -m unittest tests.test_live_sources -v
```

## Shared module

Edit `shared/nsemkt.py`, then run:

```bash
python scripts/sync_shared.py
```

CI rejects drift between the canonical file and standalone skill copies.

## Pull-request requirements

- deterministic tests with no network by default
- no secrets or live broker calls
- source/date for charge, holiday, lot-size or exchange-rule changes
- honest labels for estimates and delayed data
- update README and relevant `SKILL.md` when behavior changes
