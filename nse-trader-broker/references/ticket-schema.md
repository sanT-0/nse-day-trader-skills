# Portable manual ticket schema v1.0

`nse-trader-broker` writes `ticket.json` so any application can display or
archive a risk-approved plan without a broker SDK.

```json
{
  "schema_version": "1.0",
  "ticket": "20261101-RELIANCE-1",
  "status": "AWAITING_APPROVAL",
  "risk_passed_ist": "2026-11-02T10:00:00+05:30",
  "broker": "generic",
  "exchange": "NSE",
  "segment": "CASH",
  "instrument": "EQUITY",
  "product": "MIS",
  "entry_order": {
    "transaction": "BUY",
    "order_type": "LIMIT",
    "symbol": "RELIANCE",
    "quantity": 21,
    "price": 1166.0,
    "validity": "DAY"
  },
  "protective_exit": {
    "activate_only_after_full_entry_fill": true,
    "oco_preferred": true,
    "stop": {
      "transaction": "SELL",
      "order_type": "SL-M",
      "quantity": 21,
      "trigger_price": 1158.0
    },
    "target": {
      "transaction": "SELL",
      "order_type": "LIMIT",
      "quantity": 21,
      "price": 1182.0
    }
  },
  "estimated_charges": {},
  "max_loss_at_stop": 193.92,
  "flat_by_ist": "15:15",
  "execution": "MANUAL_ONLY"
}
```

## Contract

- `execution` is always `MANUAL_ONLY` in this project.
- The protective exit is not active until the entry is fully filled.
- `oco_preferred` is guidance, not proof the chosen broker supports OCO.
- Product labels may need broker-specific mapping.
- Estimated charges and margin are advisory; the contract note and broker UI
  are authoritative.
- Consumers must not transform this document into an order without separate,
  explicit user authorization and their own broker/risk controls.
