# Custom broker profiles

The default `generic` profile is a visible Rs 20-per-executed-order placeholder,
not a guaranteed upper bound. Use your broker's official pricing page to build
a JSON file with these rules:

```json
{
  "name": "my-broker-current-plan",
  "cash_intraday": {"rate": 0.0003, "minimum": 0, "maximum": 20},
  "cash_delivery": {"flat": 0},
  "futures": {"flat": 20},
  "options": {"flat": 20}
}
```

Then run:

```bash
python scripts/budget.py --capital 100000 --max-loss 500 \
  --broker-profile /path/to/my-broker.json
```

A rule uses either `flat`, or `rate` with optional `minimum` and `maximum`.
Missing rules inherit from the selected built-in profile. Never put API keys or
account information in this file. Verify all estimates against the contract
note.
