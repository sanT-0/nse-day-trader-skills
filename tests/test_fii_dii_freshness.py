"""FII/DII session-date and freshness guarantees.

Daily FII/DII aggregates are published by NSE after market close, so a number
must never be displayed or scored without its own session date/status, and
previous-session, stale or undated figures must not pass as live intraday flow.
Tests use frozen IST timestamps so no network or live clock is needed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.helpers import ROOT, load_module, load_shared

OPEN_MONDAY = dt.datetime(2026, 11, 2, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
AFTER_CLOSE_MONDAY = dt.datetime(2026, 11, 2, 19, 30, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
FRIDAY = "2026-10-30"  # latest completed session before Monday 2026-11-02


class FiiDiiFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nse = load_shared()
        scripts = ROOT / "nse-trader-market" / "scripts"
        cls.market = load_module("market_freshness_test", scripts / "market.py", scripts)

    def test_case_a_previous_session_is_labelled_not_live(self):
        meta = self.nse.fii_dii_freshness("30-Oct-2026", now=OPEN_MONDAY)
        self.assertEqual(meta["data_status"], "PREVIOUS_SESSION")
        self.assertEqual(meta["data_date"], FRIDAY)
        self.assertEqual(meta["market_session_date"], FRIDAY)
        self.assertTrue(meta["is_previous_session"])
        self.assertFalse(meta["is_live"])
        # Friday data on Monday IS the latest completed session, judged by
        # trading sessions (0 behind), never by calendar age.
        self.assertEqual(meta["latest_completed_session"], FRIDAY)
        self.assertEqual(meta["freshness_status"], "FRESH")
        self.assertEqual(meta["sessions_behind"], 0)
        self.assertEqual(meta["calendar_age_days"], 3)
        self.assertTrue(meta["calendar_verified"])
        self.assertNotIn("Stale", meta["freshness_note"])

    def test_case_a_dataset_keeps_date_attached_to_values(self):
        dataset = self.nse.fii_dii_dataset([
            {"date": "30 Oct 2026", "category": "FII/FPI", "netValue": "1,250", "buyValue": "9,000", "sellValue": "7,750"},
            {"date": "30 Oct 2026", "category": "DII", "netValue": "850"},
        ], now=OPEN_MONDAY)
        self.assertEqual(dataset["data_date"], FRIDAY)
        self.assertEqual(dataset["market_session_date"], FRIDAY)
        self.assertEqual(dataset["data_status"], "PREVIOUS_SESSION")
        self.assertFalse(dataset["is_live"])
        self.assertTrue(dataset["is_previous_session"])
        self.assertEqual(dataset["fii_net"], 1250.0)
        self.assertEqual(dataset["dii_net"], 850.0)
        self.assertEqual(dataset["fii_net_cr"], 1250.0)
        self.assertEqual(dataset["dii_net_cr"], 850.0)
        self.assertEqual(dataset["combined_net_cr"], 2100.0)
        self.assertIn("retrieved_at", dataset)
        self.assertEqual(dataset["retrieved_at"], OPEN_MONDAY.isoformat(timespec="seconds"))

    def test_case_b_after_market_close_is_end_of_day_not_live(self):
        meta = self.nse.fii_dii_freshness("02-Nov-2026", now=AFTER_CLOSE_MONDAY)
        self.assertEqual(meta["data_status"], "END_OF_DAY")
        self.assertEqual(meta["data_date"], "2026-11-02")
        self.assertEqual(meta["market_session_date"], "2026-11-02")
        self.assertFalse(meta["is_live"])
        self.assertFalse(meta["is_previous_session"])

    def test_case_c_missing_date_is_unknown_and_not_assumed_current(self):
        for missing in (None, "", "not-a-date"):
            with self.subTest(missing=missing):
                meta = self.nse.fii_dii_freshness(missing, now=OPEN_MONDAY)
                self.assertEqual(meta["data_status"], "UNKNOWN")
                self.assertIsNone(meta["data_date"])
                self.assertTrue(meta["warnings"])
                self.assertFalse(meta["is_live"])
                self.assertNotEqual(meta["market_session_date"], "not-a-date")

        dataset = self.nse.fii_dii_dataset([
            {"category": "FII", "netValue": "1,250"},
        ], now=OPEN_MONDAY)
        self.assertEqual(dataset["data_status"], "UNKNOWN")
        self.assertIsNone(dataset["data_date"])
        self.assertTrue(dataset["warnings"])

    def test_case_d_stale_data_is_flagged_and_warned(self):
        meta = self.nse.fii_dii_freshness("2026-10-27", now=OPEN_MONDAY)  # older than Friday
        self.assertEqual(meta["data_status"], "STALE")
        self.assertEqual(meta["data_date"], "2026-10-27")
        self.assertEqual(meta["freshness_status"], "STALE")
        self.assertEqual(meta["sessions_behind"], 3)  # 28, 29, 30 Oct trading days
        self.assertTrue(any("older than the latest completed" in w for w in meta["warnings"]))
        self.assertTrue(meta["is_previous_session"])
        self.assertFalse(meta["is_live"])
        with self.assertRaises(KeyError):
            # No status may ever be presented as live without a live source.
            self.nse.FIIDII_STATUS_NOTES["LIVE_STALE"]

    def test_case_c_one_session_behind_is_delayed_not_calendar_stale(self):
        # Wednesday's latest completed session is Tuesday; Monday data is
        # delayed (1 completed session behind), judged in trading sessions.
        now = dt.datetime(2026, 11, 4, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        meta = self.nse.fii_dii_freshness("2026-11-02", now=now)
        self.assertEqual(meta["data_status"], "STALE")
        self.assertEqual(meta["freshness_status"], "DELAYED")
        self.assertEqual(meta["latest_completed_session"], "2026-11-03")
        self.assertEqual(meta["sessions_behind"], 1)
        self.assertTrue(any("one completed trading session behind" in w for w in meta["warnings"]))
        line = self.nse.fii_dii_freshness_line(meta)
        self.assertIn("Delayed", line)
        self.assertIn("Trading sessions behind: 1", line)

    def test_freshness_line_distinguishes_live_flow_and_calendar_age(self):
        meta = self.nse.fii_dii_freshness("2026-10-30", now=OPEN_MONDAY)
        line = self.nse.fii_dii_freshness_line(meta)
        self.assertIn("Freshness: Latest available completed session", line)
        self.assertIn("Calendar age: 3 day(s)", line)
        self.assertIn("Trading sessions behind: 0", line)
        self.assertIn("Live intraday flow: No", line)
        self.assertNotIn("Stale", line)
        lines = self.nse.fii_dii_display_lines(self.nse.fii_dii_dataset(
            [{"date": "30-Oct-2026", "category": "FII/FPI", "netValue": "1,250"},
             {"date": "30-Oct-2026", "category": "DII", "netValue": "850"}],
            now=OPEN_MONDAY))
        self.assertIn("- FII/FPI net: Rs +1,250.00 crore | Session: Friday, 30 Oct 2026", lines)
        self.assertIn("- DII net: Rs +850.00 crore | Session: Friday, 30 Oct 2026", lines)
        self.assertTrue(any("Trading sessions behind: 0" in item for item in lines))

    def test_current_session_figures_are_provisional_not_live(self):
        meta = self.nse.fii_dii_freshness("2026-11-02", now=OPEN_MONDAY)
        self.assertEqual(meta["data_status"], "CURRENT_SESSION")
        self.assertEqual(meta["market_session_date"], "2026-11-02")
        self.assertFalse(meta["is_live"])  # daily aggregate, never live tick flow

    def test_future_dated_data_is_unknown(self):
        meta = self.nse.fii_dii_freshness("2026-11-03", now=OPEN_MONDAY)
        self.assertEqual(meta["data_status"], "UNKNOWN")
        self.assertTrue(meta["warnings"])

    def test_fii_dii_mismatched_dates_warn(self):
        dataset = self.nse.fii_dii_dataset([
            {"date": "30-Oct-2026", "category": "FII", "netValue": "1,250"},
            {"date": "29-Oct-2026", "category": "DII", "netValue": "850"},
        ], now=OPEN_MONDAY)
        self.assertTrue(any("different source dates" in w for w in dataset["warnings"]))

    def test_no_records_is_unknown_with_values_none(self):
        dataset = self.nse.fii_dii_dataset([], now=OPEN_MONDAY)
        self.assertEqual(dataset["data_status"], "UNKNOWN")
        self.assertIsNone(dataset["fii_net"])
        self.assertIsNone(dataset["dii_net"])
        self.assertIsNone(dataset["combined_net_cr"])
        self.assertTrue(dataset["warnings"])

    def test_freshness_reports_calendar_year_coverage(self):
        meta = self.nse.fii_dii_freshness("2026-10-30", now=OPEN_MONDAY)
        self.assertEqual(meta["calendar_years"], [2026])
        self.assertEqual(meta["calendar_verified_years"], [2026])

    def test_oversized_gap_is_stale_without_exact_count(self):
        # Add an old-year holiday so the local calendar can "verify" 2024;
        # a >400-day-old observation is STALE with no session count claim.
        self.nse.HOLIDAYS["2024-12-25"] = "Christmas (test coverage)"
        try:
            meta = self.nse.fii_dii_freshness("2024-06-15", now=OPEN_MONDAY)
        finally:
            del self.nse.HOLIDAYS["2024-12-25"]
        self.assertEqual(meta["data_status"], "STALE")
        self.assertEqual(meta["freshness_status"], "STALE")
        self.assertIsNone(meta["sessions_behind"])
        self.assertTrue(meta["calendar_verified"])
        self.assertTrue(any("gap exceeds" in w for w in meta["warnings"]))

    def test_old_data_in_uncovered_year_says_unknown_not_fresh(self):
        # 2024 has no local calendar coverage: a stale date there must NOT be
        # confidently "STALE-FRESH"-adjacent; it degrades to UNKNOWN freshness.
        meta = self.nse.fii_dii_freshness("2024-06-15", now=OPEN_MONDAY)
        self.assertFalse(meta["calendar_verified"])
        self.assertEqual(meta["calendar_years"], [2024, 2026])
        self.assertEqual(meta["calendar_verified_years"], [2026])
        self.assertEqual(meta["freshness_status"], "UNKNOWN")
        self.assertFalse(meta["is_live"])
        self.assertTrue(any("calendar is not verified" in w for w in meta["warnings"]))

    def test_score_excludes_stale_and_undated_flows(self):
        base = {
            "nifty": {"above_sma20": True, "above_sma50": True, "sma20": 22_000,
                      "sma50": 21_000, "change_1d_pct": 1.0},
            "bank": None, "vix": None, "breadth": None, "sectors": None,
        }
        current = {**base, "flows": {"fii_net_cr": 1_000.0, "dii_net_cr": 500.0,
                                     "combined_net_cr": 1_500.0,
                                     "data_date": FRIDAY, "data_status": "PREVIOUS_SESSION"}}
        detail = {c["name"]: c for c in self.market.calculate_market_score(current)["components"]}
        self.assertTrue(detail["Institutional flows"]["available"])
        self.assertIn(FRIDAY, detail["Institutional flows"]["detail"])
        self.assertIn("context only, not live intraday flow", detail["Institutional flows"]["detail"])

        for status in ("STALE", "UNKNOWN"):
            with self.subTest(status=status):
                snapshot = {**base, "flows": {"fii_net_cr": 1_000.0, "dii_net_cr": 500.0,
                                              "combined_net_cr": 1_500.0,
                                              "data_date": "2026-10-27", "data_status": status}}
                components = {c["name"]: c for c in self.market.calculate_market_score(snapshot)["components"]}
                flow_component = components["Institutional flows"]
                self.assertFalse(flow_component["available"])
                self.assertIsNone(flow_component["points"])
                self.assertIn("excluded", flow_component["detail"])

        undated = {**base, "flows": {"fii_net_cr": 1_000.0, "dii_net_cr": 500.0,
                                     "combined_net_cr": 1_500.0}}
        components = {c["name"]: c for c in self.market.calculate_market_score(undated)["components"]}
        self.assertFalse(components["Institutional flows"]["available"])

    def test_case_e_markdown_shows_session_date_next_to_numbers(self):
        flows = self.nse.fii_dii_dataset([
            {"date": "30-Oct-2026", "category": "FII/FPI", "netValue": "1,250"},
            {"date": "30-Oct-2026", "category": "DII", "netValue": "850"},
        ], now=OPEN_MONDAY)
        nifty = {"label": "NIFTY 50", "close": 25_000.0, "change_1d_pct": 0.5,
                 "change_5d_pct": 1.0, "change_20d_pct": 2.0, "trend": "UPTREND"}
        score = self.market.calculate_market_score(
            {"nifty": nifty, "bank": None, "vix": None, "breadth": None,
             "sectors": None, "flows": flows})
        snapshot = {
            "generated_ist": OPEN_MONDAY.isoformat(timespec="seconds"),
            "as_of_date": "2026-11-02",
            "snapshot_type": "LIVE_SESSION_PROVISIONAL",
            "universe": "nifty100", "universe_total": 100, "universe_scanned": 100,
            "scope_pct": 100.0,
            "nifty": nifty,
            "breadth": None, "sectors": None,
            "flows": flows,
            "score": score,
            "confidence": "LOW",
            "interpretation": self.market.interpretation("POSITIVE"),
            "errors": [], "sources": {},
        }
        markdown = self.market.build_markdown(snapshot)
        self.assertIn(
            "- FII/FPI net: Rs +1,250.00 crore | Session: Friday, 30 Oct 2026", markdown)
        self.assertIn(
            "- DII net: Rs +850.00 crore | Session: Friday, 30 Oct 2026", markdown)
        self.assertIn(
            "- Combined: Rs +2,100.00 crore | Session: Friday, 30 Oct 2026", markdown)
        self.assertIn("(data_date 2026-10-30; PREVIOUS_SESSION)", markdown)
        self.assertIn("Freshness: Latest available completed session", markdown)
        self.assertIn("Trading sessions behind: 0", markdown)
        self.assertIn("Live intraday flow: No", markdown)
        self.assertIn("not live intraday institutional flow", markdown)
        self.assertNotIn("is stale", markdown.lower().split("## Limitations")[0])
        # The score component detail also carries the session date and context.
        component = next(c for c in snapshot["score"]["components"]
                         if c["name"] == "Institutional flows")
        self.assertIn("session 2026-10-30", component["detail"])
        self.assertIn("0 completed session(s) behind", component["detail"])
        self.assertIn("context only", component["detail"])

    def test_case_e_entry_script_does_not_consume_fii_dii(self):
        source = (ROOT / "nse-trader-entry" / "scripts" / "entry.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("fiidii", source.lower())
        self.assertNotIn("flows.json", source)


class UnverifiedCalendarTests(unittest.TestCase):
    """Requirement E: an incomplete/exchange calendar must not be silently trusted."""

    @classmethod
    def setUpClass(cls):
        cls.previous_offline = os.environ.get("NSE_TRADER_OFFLINE")
        os.environ["NSE_TRADER_OFFLINE"] = "1"  # suppress any calendar refresh
        cls.nse = load_shared()

    @classmethod
    def tearDownClass(cls):
        if cls.previous_offline is None:
            os.environ.pop("NSE_TRADER_OFFLINE", None)
        else:
            os.environ["NSE_TRADER_OFFLINE"] = cls.previous_offline

    def test_case_e_unverified_calendar_reports_unknown_freshness(self):
        # 2030 is absent from the bundled calendar and refresh is suppressed,
        # so reliance on weekends-only logic must surface as UNKNOWN freshness
        # even when the naive weekend-only classification says FRESH/STALE.
        now = dt.datetime(2030, 1, 16, 10, 0,
                          tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        meta = self.nse.fii_dii_freshness("2030-01-14", now=now)
        self.assertFalse(meta["calendar_verified"])
        self.assertEqual(meta["freshness_status"], "UNKNOWN")
        self.assertTrue(any("calendar is not verified" in w for w in meta["warnings"]))
        line = self.nse.fii_dii_freshness_line(meta)
        self.assertIn("Unknown", line)
        self.assertIn("calendar: unverified", line)

    def test_case_e_unverified_calendar_does_not_claim_fresh(self):
        now = dt.datetime(2030, 1, 16, 10, 0,
                          tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        metadata = self.nse.fii_dii_freshness("2030-01-16", now=now)  # data == "today"
        self.assertEqual(metadata["data_status"], "CURRENT_SESSION")
        self.assertEqual(metadata["freshness_status"], "UNKNOWN")
        self.assertFalse(metadata["is_live"])
        self.assertTrue(metadata["warnings"])

    def test_calendar_verification_flag_never_triggers_network_laterally(self):
        # allow_network=False is strictly local: covered year → True, unknown
        # year → False, without any refresh attempt or offline kill-switch.
        self.assertTrue(self.nse.holiday_calendar_verified(2026, allow_network=False))
        self.assertFalse(self.nse.holiday_calendar_verified(2030, allow_network=False))

    def test_local_holidays_parameter_matches_holiday_name_semantics(self):
        today = dt.date(2026, 11, 2)  # Monday, not a bundled holiday
        local = self.nse.nse_holidays(allow_network=False)
        # holiday_name path (default) and injected local map agree offline.
        self.assertEqual(
            self.nse.is_trading_day(today),
            self.nse.is_trading_day(today, local),
        )
        custom = dict(local); custom[today.isoformat()] = "Test holiday"
        self.assertFalse(self.nse.is_trading_day(today, custom))

    def test_locally_covered_year_never_primes_the_cache_or_network(self):
        # Regression: a locally-covered year must not fetch the holiday
        # master or write nse-trader/cache/ as a side effect of verification.
        with mock.patch.object(self.nse, "nse_holidays", wraps=self.nse.nse_holidays) as spy:
            self.assertTrue(self.nse.holiday_calendar_verified(2026, allow_network=True))
            network_attempts = [
                call for call in spy.call_args_list
                if call.kwargs.get("allow_network") is True
            ]
            self.assertEqual(network_attempts, [])


class HolidayCalendarFreshnessTests(unittest.TestCase):
    """Weekend + holiday behaviour with a controlled NSE holiday cache.

    Sets NSE_TRADER_STATE_DIR to a temp dir whose cache marks Monday
    (2026-11-02) as an NSE trading holiday, exercising the exchange calendar
    rather than calendar-day arithmetic.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cache_dir = Path(cls.temp.name) / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "nse_holidays.json").write_text(
            json.dumps({
                "fetched_utc": "2026-11-01T10:00:00+00:00",
                "source": "tests/test_fii_dii_freshness.py",
                "holidays": {"2026-11-02": "Test-observed NSE holiday (Monday)"},
            }),
            encoding="utf-8",
        )
        cls.previous_state_dir = os.environ.get("NSE_TRADER_STATE_DIR")
        os.environ["NSE_TRADER_STATE_DIR"] = cls.temp.name
        cls.nse = load_shared()

    @classmethod
    def tearDownClass(cls):
        if cls.previous_state_dir is None:
            os.environ.pop("NSE_TRADER_STATE_DIR", None)
        else:
            os.environ["NSE_TRADER_STATE_DIR"] = cls.previous_state_dir
        cls.temp.cleanup()

    def test_case_b_friday_data_on_tuesday_after_monday_holiday_is_fresh(self):
        # Sat/Sun + Monday holiday intervene; Friday is still the latest
        # completed session, hence FRESH with 0 sessions behind.
        now = dt.datetime(2026, 11, 3, 10, 0,
                          tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        meta = self.nse.fii_dii_freshness("30-Oct-2026", now=now)
        self.assertEqual(meta["data_status"], "PREVIOUS_SESSION")
        self.assertEqual(meta["latest_completed_session"], FRIDAY)
        self.assertEqual(meta["freshness_status"], "FRESH")
        self.assertEqual(meta["sessions_behind"], 0)
        self.assertEqual(meta["calendar_age_days"], 4)  # calendar age ≠ staleness
        self.assertTrue(meta["calendar_verified"])
        self.assertFalse(meta["is_live"])
        line = self.nse.fii_dii_freshness_line(meta)
        self.assertIn("Freshness: Latest available completed session", line)
        self.assertIn("Trading sessions behind: 0", line)
        self.assertNotIn("Stale", line)

    def test_case_d_long_weekend_latest_completed_session_follows_calendar(self):
        # Tuesday post-close after the long weekend: Friday is DELAYED (one
        # completed session behind Tuesday), but Tuesday evening data is fresh.
        tuesday_open = dt.datetime(2026, 11, 3, 10, 0,
                                   tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        stale = self.nse.fii_dii_freshness("2026-10-30", now=tuesday_open)
        self.assertEqual(stale["latest_completed_session"], FRIDAY)
        self.assertEqual(stale["freshness_status"], "FRESH")

        tuesday_close = dt.datetime(2026, 11, 3, 19, 30,
                                    tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        delayed = self.nse.fii_dii_freshness("2026-10-30", now=tuesday_close)
        self.assertEqual(delayed["latest_completed_session"], "2026-11-03")
        self.assertEqual(delayed["freshness_status"], "DELAYED")
        self.assertEqual(delayed["sessions_behind"], 1)  # Tuesday only (Monday = holiday)
        self.assertEqual(delayed["data_status"], "STALE")
        self.assertTrue(any(
            "one completed trading session behind" in w for w in delayed["warnings"]))

        fresh = self.nse.fii_dii_freshness("2026-11-03", now=tuesday_close)
        self.assertEqual(fresh["data_status"], "END_OF_DAY")
        self.assertEqual(fresh["freshness_status"], "FRESH")
        self.assertEqual(fresh["sessions_behind"], 0)

    def test_case_a_friday_on_monday_holiday_is_still_latest_completed(self):
        # Monday is the exchange holiday in this cache; its only "fresh" flow
        # data remains Friday's, and it must not be marked stale.
        now = dt.datetime(2026, 11, 2, 10, 0,
                          tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        meta = self.nse.fii_dii_freshness("2026-11-02", now=now)  # holiday date itself
        self.assertEqual(meta["data_status"], "UNKNOWN")  # holiday data cannot exist
        self.assertTrue(any(
            "does not match a recent trading session" in w for w in meta["warnings"]))

        friday = self.nse.fii_dii_freshness("2026-10-30", now=now)
        self.assertEqual(friday["data_status"], "PREVIOUS_SESSION")
        self.assertEqual(friday["freshness_status"], "FRESH")


if __name__ == "__main__":
    unittest.main()
