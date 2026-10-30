import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.circuit_breaker import DEFAULT_STATE, load_state, update_and_evaluate
from scripts.mcp_health import decide_mode, validate_source_evidence
from scripts.position_calc import evaluate, position_pct
from scripts.report_lint import lint_data_points, lint_text
from scripts.run_pipeline import (
    DEFAULT_PROFILE,
    load_profile,
    validate_market_data,
    validate_value_sources,
)
from scripts.tech_score import tech_score


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)

    def _evidence(self, name, source_id, timestamp="2026-10-28T07:55:00Z"):
        return {
            "name": name,
            "independent_source_id": source_id,
            "ok": True,
            "sample_timestamp": timestamp,
            "sample_field": "index_change_pct",
            "sample_value": 0.12,
        }

    def test_two_independent_p0_sources_enable_mode_a(self):
        evidence = validate_source_evidence(
            [self._evidence("tdx", "tdx"), self._evidence("ifind", "ifind")],
            ["tdx", "ifind"],
            now=self.now,
        )
        self.assertEqual(2, sum(item["ok"] for item in evidence))
        mode, _, _, _ = decide_mode(["通达信", "同花顺iFinD"], [], [], source_evidence=evidence)
        self.assertEqual("A", mode)

    def test_network_reachability_and_names_do_not_count_as_mcp_evidence(self):
        mode, _, _, gates = decide_mode(
            ["通达信", "同花顺iFinD"], [], [], probe_ok=True, source_evidence=[]
        )
        self.assertEqual("C", mode)
        self.assertEqual(0, gates["n_verified_independent"])

    def test_duplicate_independent_id_counts_once(self):
        evidence = validate_source_evidence(
            [self._evidence("tdx", "same"), self._evidence("ifind", "same")],
            ["tdx", "ifind"],
            now=self.now,
        )
        mode, _, _, gates = decide_mode(
            ["通达信", "同花顺iFinD"], [], [], source_evidence=evidence
        )
        self.assertEqual("B", mode)
        self.assertEqual(1, gates["n_verified_independent"])

    def test_missing_stale_and_future_timestamps_are_rejected(self):
        rows = [
            {**self._evidence("tdx", "missing"), "sample_timestamp": None},
            self._evidence("ifind", "stale", "2026-10-01T00:00:00Z"),
            self._evidence("eastmoney", "future", "2026-10-29T00:00:00Z"),
        ]
        result = validate_source_evidence(
            rows, ["tdx", "ifind", "eastmoney"], now=self.now
        )
        self.assertTrue(all(not row["ok"] for row in result))


class CircuitBreakerTests(unittest.TestCase):
    def test_weekly_reduction_is_idempotent_and_does_not_mutate_input(self):
        state = {**DEFAULT_STATE, "week_pnl_pct": -6.0, "position_scale": 0.2}
        first = update_and_evaluate(state, "2026-10-28")
        second = update_and_evaluate(state, "2026-10-28")
        self.assertEqual(0.7, first["position_scale"])
        self.assertEqual(first, second)
        self.assertEqual(0.2, state["position_scale"])

    def test_eight_percent_drawdown_fails_closed_without_explicit_halt(self):
        state = {**DEFAULT_STATE, "drawdown_pct": 8.0}
        result = update_and_evaluate(state, "2026-10-28")
        self.assertFalse(result["allow_new_open"])
        self.assertEqual(0.5, result["position_scale"])

    def test_compact_dates_are_rejected_instead_of_compared_as_strings(self):
        state = {**DEFAULT_STATE, "halt_new_open_until": "20261001"}
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            update_and_evaluate(state, "2026-10-28")

    def test_invalid_state_is_rejected(self):
        state = {**DEFAULT_STATE, "drawdown_pct": 101.0}
        with self.assertRaises(ValueError):
            update_and_evaluate(state, "2026-10-28")

    def test_state_file_must_contain_a_json_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "account-state.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "顶层必须是 JSON 对象"):
                load_state(path)


class PositionAndScoreTests(unittest.TestCase):
    def test_position_formula_matches_documented_example(self):
        result = position_pct(10, 9.4, 20, 15, 1)
        self.assertEqual(15.0, result["final_position_pct"])
        self.assertEqual(6.0, result["stop_distance_pct"])

    def test_missing_gates_never_allow_open(self):
        result = evaluate(
            {
                "entry_price": 10,
                "stop_price": 9.4,
                "style": "波段",
                "signal_grade": "S",
            }
        )
        self.assertFalse(result["allow_open"])
        self.assertGreaterEqual(len(result["gate_failures"]), 5)

    def test_all_positive_score_weights_sum_to_100(self):
        flags = {
            "gmma_bull": True,
            "gmma_dispersion": True,
            "above_cloud": True,
            "tenkan_gt_kijun": True,
            "tk_golden": True,
            "cloud_thick": True,
        }
        result = tech_score(flags, adx=41, turnover_yi=12)
        self.assertEqual(100, result["score"])
        self.assertEqual(100, result["max_score"])

    def test_non_finite_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            position_pct(10, 9, 10, float("inf"), 1)
        with self.assertRaises(ValueError):
            tech_score({}, adx=float("nan"), turnover_yi=1)
        with self.assertRaises(ValueError):
            tech_score({}, adx=True, turnover_yi=1)
        with self.assertRaises(ValueError):
            evaluate({"entry_price": True, "stop_price": 0.9})


class DataAndLintTests(unittest.TestCase):
    def test_market_fields_need_two_independent_sources_and_fresh_timestamps(self):
        now = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
        field = {
            "value": 100.0,
            "timestamp": "2026-10-28T07:55:00Z",
            "sources": [
                {
                    "independent_source_id": "tdx",
                    "ok": True,
                    "value": 100.0,
                    "timestamp": "2026-10-28T07:55:00Z",
                },
                {
                    "independent_source_id": "ifind",
                    "ok": True,
                    "value": 100.0,
                    "timestamp": "2026-10-28T07:55:00Z",
                },
            ],
        }
        valid = {
            "index_close": field,
            "turnover": field,
            "limit_up_count": {
                **field,
                "value": 42,
                "sources": [{**source, "value": 42} for source in field["sources"]],
            },
        }
        self.assertEqual("PASS", validate_market_data(valid, now=now)["status"])
        invalid = dict(valid)
        invalid["turnover"] = {**field, "sources": field["sources"][:1]}
        self.assertEqual("BLOCKED", validate_market_data(invalid, now=now)["status"])

    def test_market_source_conflicts_are_blocked(self):
        now = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
        evidence = validate_value_sources(
            100.0,
            [
                {"independent_source_id": "tdx", "ok": True, "value": 100, "timestamp": "2026-10-28T07:55:00Z"},
                {"independent_source_id": "ifind", "ok": True, "value": 100.2, "timestamp": "2026-10-28T07:55:00Z"},
            ],
            "entry",
            now,
        )
        self.assertEqual("BLOCKED", evidence["status"])

    def test_numeric_string_reference_price_is_rejected(self):
        now = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
        evidence = validate_value_sources(
            "20",
            [
                {"independent_source_id": "tdx", "ok": True, "value": 10.0, "timestamp": "2026-10-28T07:55:00Z"},
                {"independent_source_id": "ifind", "ok": True, "value": 10.005, "timestamp": "2026-10-28T07:55:00Z"},
            ],
            "entry",
            now,
        )
        self.assertEqual("BLOCKED", evidence["status"])
        self.assertTrue(any("汇总值必须是有限数值" in error for error in evidence["errors"]))

    def test_profile_invalid_json_is_not_silently_defaulted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            path.write_text("{broken", encoding="utf-8")
            result = load_profile(path)
        self.assertEqual("ERROR", result["status"])
        self.assertEqual(0.5, DEFAULT_PROFILE["per_trade_risk_pct"])

    def test_lint_requires_report_sections_and_rejects_mode_c_buy_list(self):
        errors, _, _ = lint_text("模式 C 网络弱源，明日买入清单")
        self.assertTrue(any("模式 C" in error for error in errors))
        complete = "\n".join(
            (
                "数据源状态 元信息 宏观消息 大盘指数 板块资金 个股技术 心态纪律 明日策略 五维总结 不构成投资建议",
                "来源：测试源",
            )
        )
        self.assertEqual([], lint_text(complete)[0])

    def test_data_point_lint_requires_sources_and_reason_for_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "points.json"
            path.write_text(
                json.dumps(
                    [
                        {"field": "index", "value": 100, "confidence": "高"},
                        {"field": "missing", "value": "【缺失】"},
                    ]
                ),
                encoding="utf-8",
            )
            errors, _ = lint_data_points(path)
        self.assertEqual(3, len(errors))


if __name__ == "__main__":
    unittest.main()
