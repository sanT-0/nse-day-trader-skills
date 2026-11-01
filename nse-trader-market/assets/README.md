# Bundled breadth universes

`nifty50.txt` and `nifty100.txt` are standalone copies of the official NSE
constituent snapshots used by `nse-trader-market` for breadth calculations.

Refresh both this skill and the scanner snapshots from the repository root:

```bash
python scripts/update_reference_data.py
```

Review constituent diffs before release because additions/removals change
breadth history and market-score comparability.
