import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PipelineIntegrationTests(unittest.TestCase):
    def _write_json(self, path: Path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_complete_evidence_can_pass_all_gates(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            sources = [
                {"name": name, "independent_source_id": source_id, "ok": True,
                 "sample_timestamp": now, "sample_field": "index_change_pct",
                 "sample_value": 0.12}
                for name, source_id in (("tdx", "tdx"), ("ifind", "ifind"))
            ]
            probe = self._write_json(base / "probe.json", {"sources": sources})
            market_field = {
                "value": 100.0,
                "timestamp": now,
                "sources": [
                    {"independent_source_id": "tdx", "ok": True, "value": 100.0, "timestamp": now},
                    {"independent_source_id": "ifind", "ok": True, "value": 100.0, "timestamp": now},
                ],
            }
            market = self._write_json(
                base / "market.json",
                {
                    "index_close": market_field,
                    "turnover": market_field,
                    "limit_up_count": {
                        **market_field,
                        "value": 42,
                        "sources": [{**source, "value": 42} for source in market_field["sources"]],
                    },
                },
            )
            profile = self._write_json(
                base / "profile.json",
                {
                    "risk_level": "稳健",
                    "account_type": "模拟",
                    "per_trade_risk_pct": 1,
                    "single_stock_cap_pct": 15,
                    "sector_cap_pct": 20,
                    "allow_short_line": True,
                    "allow_limit_up_board": False,
                    "preferred_style": "波段",
                    "output_mode": "full",
                    "benchmark": "沪深300",
                },
            )
            from scripts.circuit_breaker import DEFAULT_STATE
            state = self._write_json(base / "account.json", DEFAULT_STATE)
            candidate = {
                "symbol": "000001",
                "sector": "示例行业",
                "entry": 10,
                "entry_sources": [
                    {"independent_source_id": "tdx", "ok": True, "value": 10.0, "timestamp": now},
                    {"independent_source_id": "ifind", "ok": True, "value": 10.005, "timestamp": now},
                ],
                "stop": 9.4,
                "style": "波段",
                "l4_calibrated": True,
                "reverse_signal_conflict": False,
                "plan_complete": True,
                "current_stock_exposure_pct": 0,
                "current_sector_exposure_pct": 0,
                "current_total_exposure_pct": 0,
                "total_position_cap_pct": 20,
                "is_limit_up_board": False,
                "adx": 41,
                "turnover_20d_avg_yi": 12,
                "flags": {
                    "gmma_bull": True,
                    "gmma_dispersion": True,
                    "above_cloud": True,
                    "tenkan_gt_kijun": True,
                    "tk_golden": True,
                    "cloud_thick": True,
                },
            }
            second_sector_candidate = {
                **candidate,
                "symbol": "000003",
                "sector": "另一行业",
            }
            tickers = self._write_json(
                base / "tickers.json",
                [
                    candidate,
                    {**candidate, "symbol": "000002"},
                    second_sector_candidate,
                ],
            )
            outdir = base / "pipeline"
            audit_dir = base / "audit"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "run_pipeline.py"),
                "--available", "tdx,ifind",
                "--probe-file", str(probe),
                "--market-data", str(market),
                "--state", str(state),
                "--profile", str(profile),
                "--tickers", str(tickers),
                "--report", str(ROOT / "examples" / "good-report.html"),
                "--outdir", str(outdir),
                "--audit-dir", str(audit_dir),
            ]
            result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            summary = json.loads(result.stdout)
            self.assertTrue(summary["overall_allow_buy_list"])
            self.assertEqual("PASS", summary["gates"]["G8_market_data"])
            self.assertEqual("PASS", summary["gates"]["G7_report_lint"])
            self.assertEqual("ALLOW_BUY_LIST", summary["tickers"][0]["final_action"])
            self.assertEqual("OBSERVE_ONLY", summary["tickers"][1]["final_action"])
            self.assertTrue(
                any("板块暴露" in reason for reason in summary["tickers"][1]["blocked_by"])
            )
            self.assertEqual("OBSERVE_ONLY", summary["tickers"][2]["final_action"])
            self.assertTrue(
                any("总仓位" in reason for reason in summary["tickers"][2]["blocked_by"])
            )

    def test_missing_evidence_report_and_market_data_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            from scripts.circuit_breaker import DEFAULT_STATE
            state = self._write_json(base / "account.json", DEFAULT_STATE)
            command = [
                sys.executable,
                str(ROOT / "scripts" / "run_pipeline.py"),
                "--available", "tdx,ifind",
                "--state", str(state),
                "--profile", str(base / "missing-profile.json"),
                "--outdir", str(base / "pipeline"),
                "--audit-dir", str(base / "audit"),
            ]
            result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(1, result.returncode, result.stderr + result.stdout)
            summary = json.loads(result.stdout)
            self.assertFalse(summary["overall_allow_buy_list"])
            self.assertEqual("C", summary["gates"]["G1_mode"])
            self.assertEqual("NOT_RUN", summary["gates"]["G7_report_lint"])
            self.assertEqual("NOT_RUN", summary["gates"]["G8_market_data"])


if __name__ == "__main__":
    unittest.main()
