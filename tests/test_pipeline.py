from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT


class OfflinePipelineTests(unittest.TestCase):
    def run_script(self, skill: str, script: str, *args: str, cwd: Path):
        return subprocess.run(
            [sys.executable, str(ROOT / skill / "scripts" / script), *map(str, args)],
            cwd=cwd, capture_output=True, text=True, timeout=60,
        )

    def test_cash_plan_size_risk_and_manual_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            out = work / "state"
            plan = self.run_script(
                "nse-trader-exit", "exit.py", "--ticker", "RELIANCE",
                "--entry", "1166", "--stop", "1158", "--target", "1182",
                "--out", out, cwd=work,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            size = self.run_script(
                "nse-trader-budget", "budget.py", "--plan", out / "plan.json",
                "--capital", "100000", "--max-loss", "500", "--out", out,
                cwd=work,
            )
            self.assertEqual(size.returncode, 0, size.stderr)
            order = json.loads((out / "orders.json").read_text(encoding="utf-8"))
            self.assertGreater(order["qty"], 0)
            self.assertLessEqual(order["max_loss_at_stop"], 500)

            risk = self.run_script(
                "nse-trader-risk", "risk.py", "--order", out / "orders.json",
                "--capital", "100000", "--now", "2026-11-02T10:00",
                "--out", out, cwd=work,
            )
            self.assertEqual(risk.returncode, 0, risk.stderr)
            self.assertIn("PASS", risk.stdout)

            ticket = self.run_script(
                "nse-trader-broker", "ticket.py", "--order", out / "orders.json",
                "--risk-state", out / "risk_state.json", "--approval",
                "offline test approval", "--out", out, cwd=work,
            )
            self.assertEqual(ticket.returncode, 0, ticket.stderr)
            self.assertIn("NO ORDER WAS SENT TO ANY BROKER", ticket.stdout)
            self.assertTrue((out / "ticket.md").is_file())
            self.assertNotIn(
                "growwapi", (out / "ticket.md").read_text(encoding="utf-8").lower()
            )
            portable = json.loads((out / "ticket.json").read_text(encoding="utf-8"))
            self.assertEqual(portable["execution"], "MANUAL_ONLY")
            self.assertEqual(portable["broker"], "generic")

    def test_option_sizing_uses_whole_lots_and_full_premium(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            out = work / "state"
            plan = self.run_script(
                "nse-trader-exit", "exit.py", "--ticker", "NIFTY26NOV26000CE",
                "--entry", "180", "--stop", "150", "--target", "240",
                "--segment", "FNO", "--instrument", "OPTION", "--out", out,
                cwd=work,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            size = self.run_script(
                "nse-trader-budget", "budget.py", "--plan", out / "plan.json",
                "--segment", "FNO", "--instrument", "OPTION", "--lot-size", "65",
                "--capital", "100000", "--max-loss", "2500", "--out", out,
                cwd=work,
            )
            self.assertEqual(size.returncode, 0, size.stderr)
            order = json.loads((out / "orders.json").read_text(encoding="utf-8"))
            self.assertEqual(order["lots"], 1)
            self.assertEqual(order["qty"], 65)
            self.assertEqual(order["instrument"], "OPTION")
            self.assertGreater(order["margin_required"], 65 * 180)
            self.assertLessEqual(order["max_loss_at_stop"], 2500)

    def test_custom_broker_profile_propagates_to_portable_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            out = work / "state"
            profile = work / "broker.json"
            profile.write_text(json.dumps({
                "name": "my-broker-test",
                "cash_intraday": {"rate": 0.0003, "maximum": 20},
                "cash_delivery": {"flat": 0},
                "futures": {"flat": 15},
                "options": {"flat": 15},
            }), encoding="utf-8")
            plan = self.run_script(
                "nse-trader-exit", "exit.py", "--ticker", "RELIANCE",
                "--entry", "1166", "--stop", "1158", "--target", "1182",
                "--out", out, cwd=work,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            size = self.run_script(
                "nse-trader-budget", "budget.py", "--plan", out / "plan.json",
                "--capital", "100000", "--max-loss", "500",
                "--broker-profile", profile, "--out", out, cwd=work,
            )
            self.assertEqual(size.returncode, 0, size.stderr)
            order = json.loads((out / "orders.json").read_text(encoding="utf-8"))
            self.assertEqual(order["broker_profile"], "my-broker-test")
            risk = self.run_script(
                "nse-trader-risk", "risk.py", "--order", out / "orders.json",
                "--capital", "100000", "--now", "2026-11-02T10:00",
                "--out", out, cwd=work,
            )
            self.assertEqual(risk.returncode, 0, risk.stderr)
            ticket = self.run_script(
                "nse-trader-broker", "ticket.py", "--order", out / "orders.json",
                "--risk-state", out / "risk_state.json", "--out", out, cwd=work,
            )
            self.assertEqual(ticket.returncode, 0, ticket.stderr)
            portable = json.loads((out / "ticket.json").read_text(encoding="utf-8"))
            self.assertEqual(portable["broker"], "my-broker-test")

    def test_broker_refuses_without_risk_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            order = {
                "ticket": "test-1", "ticker": "RELIANCE", "qty": 1,
                "entry": 100, "stop": 98, "target": 104,
            }
            (work / "order.json").write_text(json.dumps(order), encoding="utf-8")
            result = self.run_script(
                "nse-trader-broker", "ticket.py", "--order", work / "order.json",
                "--risk-state", work / "missing.json", "--out", work / "out",
                cwd=work,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("run nse-trader-risk first", result.stderr)


if __name__ == "__main__":
    unittest.main()
