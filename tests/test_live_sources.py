from __future__ import annotations

import os
import tempfile
import unittest

from tests.helpers import load_shared


@unittest.skipUnless(os.environ.get("LIVE") == "1", "set LIVE=1 for network smoke tests")
class LiveSourceTests(unittest.TestCase):
    def setUp(self):
        self.market = load_shared()
        self.temp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp.cleanup()

    def test_yahoo_nse_quote(self):
        quote = self.market.yahoo_quote("RELIANCE")
        self.assertGreater(quote["ltp"], 0)
        self.assertEqual(quote["currency"], "INR")

    def test_nse_reference_sources(self):
        self.assertGreater(len(self.market.nse_symbols(refresh=True)), 1000)
        self.assertGreater(len(self.market.fo_lots(refresh=True)), 100)
        holidays = self.market.nse_holidays(refresh=True, allow_network=True)
        self.assertIn("2026-01-26", holidays)


if __name__ == "__main__":
    unittest.main()
