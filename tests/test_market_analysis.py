from __future__ import annotations

import datetime as dt
import unittest

from tests.helpers import ROOT, load_module


class MarketAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = ROOT / "nse-trader-market" / "scripts"
        cls.market = load_module("market_analysis_test", scripts / "market.py", scripts)

    @staticmethod
    def bars(start: float, daily_step: float, count: int = 60):
        first = dt.date(2026, 8, 1)
        result = []
        price = start
        for index in range(count):
            price += daily_step
            result.append({
                "t": dt.datetime.combine(
                    first + dt.timedelta(days=index), dt.time(15, 30),
                    tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)),
                ),
                "o": price - daily_step / 2,
                "h": price + abs(daily_step),
                "l": price - abs(daily_step),
                "c": price,
                "v": 1_000_000 + index,
            })
        return result

    def test_index_metrics_identify_uptrend(self):
        metrics = self.market.calculate_series_metrics(
            "NIFTY 50", "^NSEI", self.bars(20_000, 20)
        )
        self.assertGreater(metrics["change_1d_pct"], 0)
        self.assertTrue(metrics["above_sma20"])
        self.assertTrue(metrics["above_sma50"])
        self.assertGreater(metrics["sma20"], metrics["sma50"])

    def test_breadth_uses_dominant_date_and_reports_coverage(self):
        rows = [
            {"symbol": "A", "date": "2026-10-30", "change_pct": 1.0,
             "above_sma20": True, "above_sma50": True, "new_high_20d": True,
             "new_low_20d": False},
            {"symbol": "B", "date": "2026-10-30", "change_pct": -0.5,
             "above_sma20": False, "above_sma50": True, "new_high_20d": False,
             "new_low_20d": False},
            {"symbol": "STALE", "date": "2026-10-29", "change_pct": 2.0,
             "above_sma20": True, "above_sma50": True, "new_high_20d": False,
             "new_low_20d": False},
        ]
        breadth = self.market.calculate_breadth(rows, expected_count=4)
        self.assertEqual(breadth["date"], "2026-10-30")
        self.assertEqual(breadth["valid"], 2)
        self.assertEqual(breadth["stale"], 1)
        self.assertEqual(breadth["advancers"], 1)
        self.assertEqual(breadth["decliners"], 1)
        self.assertEqual(breadth["coverage_pct"], 50.0)

    def test_score_is_transparent_and_zone_is_risk_on(self):
        snapshot = {
            "nifty": {"above_sma20": True, "above_sma50": True,
                      "sma20": 22_000, "sma50": 21_000, "change_1d_pct": 1.2},
            "bank": {"above_sma20": True, "above_sma50": True,
                     "change_1d_pct": 1.0},
            "vix": {"close": 12.5, "change_1d_pct": -4.0},
            "breadth": {"advancers_pct": 72.0, "above_sma20_pct": 74.0,
                        "above_sma50_pct": 68.0},
            "sectors": {"positive_pct": 77.8, "average_change_pct": 0.9},
            "flows": {"fii_net_cr": 1_000.0, "dii_net_cr": 500.0,
                      "combined_net_cr": 1_500.0},
        }
        score = self.market.calculate_market_score(snapshot)
        self.assertGreaterEqual(score["score"], 75)
        self.assertEqual(score["zone"], "RISK_ON")
        self.assertEqual(sum(c["max_points"] for c in score["components"]), 100)

    def test_score_degrades_to_available_components(self):
        snapshot = {
            "nifty": {"above_sma20": False, "above_sma50": False,
                      "sma20": 20_000, "sma50": 21_000, "change_1d_pct": -2.0},
            "bank": None,
            "vix": {"close": 29.0, "change_1d_pct": 8.0},
            "breadth": {"advancers_pct": 20.0, "above_sma20_pct": 25.0,
                        "above_sma50_pct": 30.0},
            "sectors": None,
            "flows": None,
        }
        score = self.market.calculate_market_score(snapshot)
        self.assertLess(score["score"], 30)
        self.assertEqual(score["zone"], "RISK_OFF")
        self.assertEqual(score["available_points"], 75)

    def test_yahoo_index_symbols_are_not_modified(self):
        self.assertEqual(self.market.nsemkt.yahoo_symbol("^NSEI"), "^NSEI")
        self.assertEqual(self.market.nsemkt.yahoo_symbol("RELIANCE"), "RELIANCE.NS")

    def test_data_confidence_requires_date_alignment(self):
        snapshot = {
            "score": {"available_points": 100},
            "nifty": {"date": "2026-10-30"},
            "breadth": {"date": "2026-10-29", "coverage_pct": 100.0},
            "sectors": {"date": "2026-10-30"},
        }
        self.assertEqual(self.market.confidence(snapshot, [], 100.0), "MEDIUM")


if __name__ == "__main__":
    unittest.main()
