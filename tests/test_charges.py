from __future__ import annotations

import unittest

from tests.helpers import load_shared


class BrokerChargeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = load_shared()

    def test_groww_cash_intraday_round_trip(self):
        result = self.market.round_trip_charges(
            "CASH", 10, 1450, 1440, "MIS", broker="groww"
        )
        self.assertEqual(result["total"], 39.22)
        self.assertEqual(result["broker_profile"], "groww-2026-11-01")
        self.assertEqual(result["buy"]["stamp"], 0.43)
        self.assertEqual(result["sell"]["stt"], 3.60)

    def test_generic_flat_profile_is_default(self):
        generic = self.market.round_trip_charges("CASH", 10, 1450, 1440, "MIS")
        groww = self.market.round_trip_charges(
            "CASH", 10, 1450, 1440, "MIS", broker="groww"
        )
        self.assertEqual(generic["broker_profile"], "generic-flat-20")
        self.assertGreater(generic["total"], groww["total"])

    def test_custom_broker_profile(self):
        custom = {
            "name": "zero-delivery-demo",
            "cash_delivery": {"flat": 0},
        }
        leg = self.market.broker_charges(
            "CASH", "BUY", 10, 100, "CNC", broker_profile=custom
        )
        self.assertEqual(leg["broker_profile"], "zero-delivery-demo")
        self.assertEqual(leg["brokerage"], 0)

    def test_long_option_round_trip(self):
        result = self.market.round_trip_charges("FNO", 65, 180, 150, "OPT")
        self.assertEqual(result["total"], 71.19)
        self.assertEqual(result["sell"]["stt"], 14.62)
        self.assertEqual(result["buy"]["brokerage"], 20.0)

    def test_futures_uses_published_sell_stt_rate(self):
        leg = self.market.broker_charges("FNO", "SELL", 500, 1164, "FUT")
        self.assertEqual(leg["stt"], 291.0)
        self.assertEqual(leg["brokerage"], 20.0)

    def test_tick_rounding_is_conservative(self):
        self.assertAlmostEqual(self.market.round_tick(101.023, "down"), 101.0)
        self.assertAlmostEqual(self.market.round_tick(101.023, "up"), 101.05)


if __name__ == "__main__":
    unittest.main()
