# Broker profiles

The skill pack is broker-neutral. It creates manual NSE tickets and never
connects to a broker. The budget step needs a brokerage assumption so charges
can be included in risk.

## Built-in profiles

| Profile | Brokerage assumption |
|---|---|
| `generic` (default) | Visible Rs 20 placeholder per executed order; customize it |
| `groww` | Published Groww schedule captured on 2026-11-01 |

The statutory and exchange estimate—STT, stamp duty, NSE transaction charges,
SEBI, IPFT and GST—is shared. It can change; your contract note is definitive.

```bash
python nse-trader-budget/scripts/budget.py \
  --capital 100000 --max-loss 500 --broker generic
```

Optional Groww profile:

```bash
python nse-trader-budget/scripts/budget.py \
  --capital 100000 --max-loss 500 --broker groww
```

## Custom broker

Copy `config/broker-profile.example.json`, update it from your broker's current
official pricing page, then pass it to the budget skill:

```bash
python nse-trader-budget/scripts/budget.py \
  --capital 100000 --max-loss 500 \
  --broker generic --broker-profile my-broker.json
```

Each market rule supports either:

```json
{"flat": 20}
```

or a turnover rate with optional limits:

```json
{"rate": 0.0003, "minimum": 0, "maximum": 20}
```

Required rule names:

- `cash_intraday`
- `cash_delivery`
- `futures`
- `options`

Missing rules inherit from the selected built-in profile. The resolved rule is
embedded in `orders.json`, allowing the risk gate to recalculate charges after
a fresh quote without knowing which application produced the order.

Never add API keys or account information to a profile.
