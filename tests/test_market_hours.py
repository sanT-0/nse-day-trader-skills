from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.helpers import load_shared


class MarketHoursTests(unittest.TestCase):
    def setUp(self):
        self.market = load_shared()
        self.temp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp.cleanup()

    def at(self, date: dt.date, hour: int, minute: int):
        return dt.datetime(date.year, date.month, date.day, hour, minute,
                           tzinfo=self.market.IST)

    def test_weekend_and_bundled_holiday(self):
        self.assertEqual(
            self.market.session_state(self.at(dt.date(2026, 11, 1), 10, 0))["state"],
            "WEEKEND",
        )
        holiday = self.market.session_state(self.at(dt.date(2026, 1, 26), 10, 0))
        self.assertEqual(holiday["state"], "HOLIDAY")
        self.assertEqual(holiday["holiday"], "Republic Day")

    def test_open_and_squareoff_windows(self):
        day = dt.date(2026, 11, 2)
        self.assertEqual(self.market.session_state(self.at(day, 10, 0))["state"], "OPEN")
        self.assertEqual(self.market.session_state(self.at(day, 15, 16))["state"], "SQUAREOFF")
        allowed, _ = self.market.can_enter_now(self.at(day, 14, 59))
        blocked, reason = self.market.can_enter_now(self.at(day, 15, 1))
        self.assertTrue(allowed)
        self.assertFalse(blocked)
        self.assertIn("cutoff", reason)

    def test_official_holiday_refresh_is_cached(self):
        payload = {
            "CM": [
                {"tradingDate": "26-Jan-2027", "description": "Republic Day"},
                {"tradingDate": "15-Aug-2027", "description": "Independence Day"},
            ]
        }
        with mock.patch.dict(os.environ, {"NSE_TRADER_OFFLINE": "0"}), \
             mock.patch.object(self.market, "http_json", return_value=payload):
            holidays = self.market.nse_holidays(refresh=True, allow_network=True)
        self.assertEqual(holidays["2027-01-26"], "Republic Day")
        cache = Path("nse-trader/cache/nse_holidays.json")
        self.assertTrue(cache.is_file())
        self.assertTrue(self.market.holiday_calendar_verified(2027))

    def test_unknown_calendar_is_explicit_when_offline(self):
        with mock.patch.dict(os.environ, {"NSE_TRADER_OFFLINE": "1"}):
            self.assertFalse(self.market.holiday_calendar_verified(2035))


if __name__ == "__main__":
    unittest.main()
