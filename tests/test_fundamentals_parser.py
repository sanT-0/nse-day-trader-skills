from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from tests.helpers import ROOT, load_module


class FundamentalsParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = ROOT / "nse-trader-analyst" / "scripts"
        cls.facts = load_module("facts_test", scripts / "facts.py", scripts)
        cls.fixture = (ROOT / "tests" / "fixtures" / "screener_quarters.html").read_text(
            encoding="utf-8"
        )

    def test_quarters_qoq_yoy_and_ttm(self):
        with mock.patch.object(self.facts.nsemkt, "http_get", return_value=self.fixture):
            company, quarters, ttm = self.facts.parse_screener("EXAMPLE")
        self.assertEqual(company, "Example Industries Ltd")
        self.assertEqual(len(quarters), 5)
        latest = quarters[-1]
        self.assertEqual(latest["period"], "Sep 2026")
        self.assertEqual(latest["revenue_qoq_pct"], 15.38)
        self.assertEqual(latest["revenue_yoy_pct"], 50.0)
        self.assertEqual(latest["profit_yoy_pct"], 80.0)
        self.assertEqual(latest["net_margin_pct"], 12.0)
        self.assertEqual(ttm["revenue_cr"], 5100.0)
        self.assertEqual(ttm["net_profit_cr"], 540.0)


if __name__ == "__main__":
    unittest.main()
