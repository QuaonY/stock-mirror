#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 一键流水线：MCP检查 → 熔断 →（可选）票面评分/仓位 → lint → 审计。"""

from __future__ import annotations

import argparse
import math
import json
import subprocess
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .position_calc import evaluate as evaluate_position
    from .tech_score import tech_score
except ImportError:
    from position_calc import evaluate as evaluate_position
    from tech_score import tech_score


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent


def run_py(script: str, args: List[str]) -> Dict[str, Any]:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    payload: Dict[str, Any] = {"returncode": proc.returncode, "cmd": cmd}
    out = (proc.stdout or "").strip()
    if out:
        try:
            payload["json"] = json.loads(out)
        except json.JSONDecodeError:
            payload["stdout"] = out[:2000]
    if proc.stderr:
        payload["stderr"] = proc.stderr[:1000]
    return payload


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


DEFAULT_PROFILE: Dict[str, Any] = {
    "risk_level": "稳健",
    "account_type": "模拟",
    "per_trade_risk_pct": 0.5,
    "single_stock_cap_pct": 10.0,
    "sector_cap_pct": 20.0,
    "allow_short_line": True,
    "allow_limit_up_board": False,
    "preferred_style": "波段",
    "output_mode": "full",
    "benchmark": "沪深300",
    "notes": "未提供有效画像，使用保守默认值",
}

REQUIRED_MARKET_FIELDS = ("index_close", "turnover", "limit_up_count")


def load_profile(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"status": "DEFAULTED", "profile": dict(DEFAULT_PROFILE), "warnings": ["未提供风险画像，使用稳健默认值"]}
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"status": "ERROR", "profile": {}, "errors": [f"风险画像不可读：{exc}"]}
    if not isinstance(profile, dict):
        return {"status": "ERROR", "profile": {}, "errors": ["风险画像必须是 JSON 对象"]}
    errors: List[str] = []
    for key in ("risk_level", "per_trade_risk_pct", "single_stock_cap_pct", "allow_short_line"):
        if key not in profile:
            errors.append(f"风险画像缺少必需字段：{key}")
    if profile.get("risk_level") not in {"保守", "稳健", "积极"}:
        errors.append("risk_level 必须是保守/稳健/积极")
    for key, low, high in (
        ("per_trade_risk_pct", 0.1, 2.0),
        ("single_stock_cap_pct", 5.0, 20.0),
        ("sector_cap_pct", 10.0, 40.0),
    ):
        if key in profile:
            value = profile[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                errors.append(f"{key} 必须是 {low} 到 {high} 之间的有限数字")
    if "allow_short_line" in profile and not isinstance(profile["allow_short_line"], bool):
        errors.append("allow_short_line 必须是布尔值")
    if "allow_limit_up_board" in profile and not isinstance(profile["allow_limit_up_board"], bool):
        errors.append("allow_limit_up_board 必须是布尔值")
    enums = {
        "account_type": {"模拟", "实盘"},
        "preferred_style": {"短线", "波段", "长线", "混合"},
        "output_mode": {"full", "summary", "plan-only"},
        "benchmark": {"沪深300", "中证1000", "万得全A"},
    }
    for key, allowed in enums.items():
        if key in profile and profile[key] not in allowed:
            errors.append(f"{key} 必须是以下值之一：{', '.join(sorted(allowed))}")
    if "notes" in profile and not isinstance(profile["notes"], str):
        errors.append("notes 必须是字符串")
    if errors:
        return {"status": "ERROR", "profile": profile, "errors": errors}
    normalized = dict(DEFAULT_PROFILE)
    normalized.update(profile)
    return {"status": "PASS", "profile": normalized, "warnings": []}


def _parse_fresh_timestamp(raw: Any, now: datetime) -> Tuple[Optional[datetime], Optional[str]]:
    if not isinstance(raw, str):
        return None, "缺少 ISO-8601 timestamp"
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
    except ValueError:
        return None, "timestamp 格式无效"
    age = now.astimezone(timezone.utc) - timestamp
    if age < timedelta(minutes=-5):
        return timestamp, "timestamp 在未来"
    if age > timedelta(days=7):
        return timestamp, "数据超过 7 天"
    return timestamp, None


def validate_value_sources(
    reference_value: Any,
    sources: Any,
    field_name: str,
    now: datetime,
    allowed_source_ids: Optional[set] = None,
) -> Dict[str, Any]:
    """核对独立来源的原始值、时间戳与分字段一致性阈值。"""
    errors: List[str] = []
    valid_sources: Dict[str, Dict[str, Any]] = {}
    reference_is_number = (
        not isinstance(reference_value, bool)
        and isinstance(reference_value, (int, float))
        and math.isfinite(reference_value)
    )
    if not reference_is_number:
        errors.append(f"{field_name} 汇总值必须是有限数值")
    elif reference_value < 0 or (
        field_name in {"index_close", "entry"} and reference_value <= 0
    ):
        errors.append(f"{field_name} 汇总值必须是有效的非负数值")
    elif field_name == "limit_up_count" and not isinstance(reference_value, int):
        errors.append("limit_up_count 汇总值必须是整数")
    if not isinstance(sources, list):
        sources = []
    for source in sources:
        if not isinstance(source, dict) or source.get("ok") is not True:
            continue
        source_id = str(source.get("independent_source_id", "")).strip()
        source_value = source.get("value")
        if not source_id:
            continue
        if allowed_source_ids is not None and source_id.casefold() not in allowed_source_ids:
            continue
        if (
            isinstance(source_value, bool)
            or not isinstance(source_value, (int, float))
            or not math.isfinite(source_value)
            or source_value < 0
            or (field_name == "limit_up_count" and not isinstance(source_value, int))
        ):
            continue
        timestamp, timestamp_error = _parse_fresh_timestamp(source.get("timestamp"), now)
        if timestamp_error:
            continue
        valid_sources.setdefault(
            source_id.casefold(),
            {"value": float(source_value), "timestamp": timestamp.isoformat()},
        )
    if len(valid_sources) < 2:
        errors.append("至少需要两个成功、独立且带时间戳的来源原始值")
    values = [item["value"] for item in valid_sources.values()]
    spread_pct: Optional[float] = None
    tolerance = 0.0 if field_name == "limit_up_count" else (0.1 if field_name in {"index_close", "entry"} else 1.0)
    if len(values) >= 2:
        if field_name == "limit_up_count":
            consistent = all(value == values[0] for value in values[1:])
            if not consistent:
                errors.append("来源间涨停数冲突")
            spread_pct = 0.0 if consistent else None
        else:
            denominator = max(max(abs(value) for value in values), 1e-12)
            spread_pct = (max(values) - min(values)) / denominator * 100.0
            if spread_pct >= tolerance:
                errors.append(
                    f"来源间差异 {spread_pct:.4f}% 达到/超过 {tolerance}% 阈值"
                )
        if reference_is_number:
            if field_name == "limit_up_count":
                reference_conflict = any(value != reference_value for value in values)
            else:
                reference_conflict = any(
                    abs(value - reference_value) / max(abs(reference_value), 1e-12) * 100.0 >= tolerance
                    for value in values
                )
            if reference_conflict:
                errors.append(f"汇总值与来源原始值差异达到/超过 {tolerance}%")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "source_values": valid_sources,
        "source_ids": sorted(valid_sources),
        "spread_pct": spread_pct,
    }


def validate_market_data(
    data: Any,
    now: Optional[datetime] = None,
    allowed_source_ids: Optional[set] = None,
) -> Dict[str, Any]:
    """检查关键市场字段、双源原始值、独立性、时间及冲突阈值。"""
    if not isinstance(data, dict):
        return {"status": "ERROR", "errors": ["市场数据必须是 JSON 对象"], "fields": {}}
    now = now or datetime.now(timezone.utc)
    fields: Dict[str, Any] = {}
    errors: List[str] = []
    for name in REQUIRED_MARKET_FIELDS:
        item = data.get(name)
        field_errors: List[str] = []
        if not isinstance(item, dict):
            field_errors.append("缺少字段对象")
            item = {}
        value = item.get("value")
        if value in (None, "", "【缺失】"):
            field_errors.append("值缺失")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            field_errors.append("值必须是有限数字")
        elif value < 0:
            field_errors.append("值不能为负数")
        elif name == "index_close" and value <= 0:
            field_errors.append("指数收盘点位必须大于 0")
        elif name == "limit_up_count" and not isinstance(value, int):
            field_errors.append("涨停数必须是整数")
        timestamp, timestamp_error = _parse_fresh_timestamp(item.get("timestamp"), now)
        if timestamp_error:
            field_errors.append(timestamp_error)
        source_check = validate_value_sources(
            value, item.get("sources"), name, now, allowed_source_ids
        )
        field_errors.extend(source_check["errors"])
        fields[name] = {
            "value": value,
            "timestamp": timestamp.isoformat() if timestamp else item.get("timestamp"),
            "source_ids": source_check["source_ids"],
            "source_values": source_check["source_values"],
            "spread_pct": source_check["spread_pct"],
            "status": "PASS" if not field_errors else "BLOCKED",
            "errors": field_errors,
        }
        errors.extend(f"{name}: {error}" for error in field_errors)
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "fields": fields}


def market_data_points(validation: Dict[str, Any], raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    for name, result in validation.get("fields", {}).items():
        raw = raw_data.get(name, {})
        points.append(
            {
                "field": name,
                "value": result.get("value") if result.get("value") is not None else "【缺失】",
                "sources": raw.get("sources", []) if isinstance(raw, dict) else [],
                "timestamp": result.get("timestamp"),
                "confidence": "高" if result.get("status") == "PASS" else "低",
                "consistent": result.get("status") == "PASS",
                "missing_reason": "; ".join(result.get("errors", [])),
            }
        )
    return points


def main() -> int:
    parser = argparse.ArgumentParser(description="StockMirror daily pipeline")
    parser.add_argument("--available", required=True, help="已连接行情源名称，逗号分隔")
    parser.add_argument("--healthy", default="1")
    parser.add_argument("--probe", action="store_true", help="仅网络连通性探测，不代表 MCP 已探活")
    parser.add_argument("--probe-file", help="宿主逐来源样例探活 JSON")
    parser.add_argument("--market-data", help="G8 关键字段双源证据 JSON")
    parser.add_argument("--state", default=str(ROOT / "state" / "account_state.json"))
    parser.add_argument("--nav", type=float)
    parser.add_argument("--peak", type=float)
    parser.add_argument("--profile", default=str(ROOT / "state" / "user_risk_profile.json"))
    parser.add_argument("--tickers", help="逐票输入 JSON 数组")
    parser.add_argument("--report", help="已有报告路径；未提供则 G7=NOT_RUN")
    parser.add_argument("--outdir", default=str(ROOT / "state" / "pipeline"))
    parser.add_argument("--audit-dir", default=str(ROOT / "state" / "audit"))
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    now = datetime.now(timezone.utc)
    summary: Dict[str, Any] = {
        "date": today,
        "started_at": now.isoformat(timespec="seconds"),
        "steps": [],
        "gates": {},
        "overall_status": "ERROR",
        "overall_allow_buy_list": False,
    }

    def record_step(name: str, status: str, **details: Any) -> None:
        summary["steps"].append({"step": name, "status": status, "ok": status == "PASS", **details})

    # G1/G2: per-source probe evidence is required; --probe is diagnostic only.
    health_args = ["--available", args.available, "--healthy", args.healthy]
    if args.probe:
        health_args.append("--probe")
    if args.probe_file:
        health_args += ["--probe-file", args.probe_file]
    health_path = outdir / f"{today}_health.json"
    health = run_py("mcp_health.py", health_args)
    health_json = health.get("json") if isinstance(health.get("json"), dict) else {}
    if health["returncode"] != 0 or not health_json:
        health_status = "ERROR"
        health_json = {
            "status": "ERROR",
            "mode": "C",
            "allow_candidates": False,
            "allow_buy_list": False,
            "error": health.get("stderr") or health.get("stdout") or "health check produced no JSON",
        }
    else:
        health_status = str(health_json.get("status", "ERROR"))
    write_json(health_path, health_json)
    mode = health_json.get("mode", "C")
    allow_candidates = health_json.get("allow_candidates") is True
    allow_buy = health_json.get("allow_buy_list") is True
    probe_details = health_json.get("probe")
    if not isinstance(probe_details, dict):
        probe_details = {}
    verified_source_ids = {
        str(row.get("independent_source_id", "")).strip().casefold()
        for row in probe_details.get("source_evidence", [])
        if isinstance(row, dict) and row.get("ok") is True
    }
    summary["gates"].update(
        {
            "G1_status": health_status,
            "G1_mode": mode,
            "G2_allow_candidates": allow_candidates,
            "G2_allow_buy_list": allow_buy,
        }
    )
    record_step("mcp_health", health_status, mode=mode, detail=health_json.get("tips", []))

    # G5: evaluate read-only; circuit_breaker.py persists only explicit updates.
    breaker_args = ["--state", args.state]
    if args.nav is not None:
        breaker_args += ["--nav", str(args.nav)]
    if args.peak is not None:
        breaker_args += ["--peak", str(args.peak)]
    breaker = run_py("circuit_breaker.py", breaker_args)
    breaker_json = breaker.get("json") if isinstance(breaker.get("json"), dict) else {}
    breaker_ok = breaker["returncode"] in (0, 1) and breaker_json.get("status") in {"PASS", "BLOCKED"}
    if not breaker_ok:
        breaker_status = "ERROR"
        allow_open = False
        breaker_json = {
            "status": "ERROR",
            "allow_new_open": False,
            "position_scale": 0.0,
            "reasons": [breaker.get("stderr") or breaker.get("stdout") or "breaker evaluation failed"],
        }
    else:
        breaker_status = str(breaker_json.get("status"))
        allow_open = breaker_json.get("allow_new_open") is True
    write_json(outdir / f"{today}_breaker.json", breaker_json)
    summary["gates"].update(
        {
            "G5_status": breaker_status,
            "G5_allow_new_open": allow_open,
            "G5_reasons": breaker_json.get("reasons", []),
            "position_scale": breaker_json.get("position_scale", 0.0),
        }
    )
    record_step("circuit_breaker", breaker_status, reasons=breaker_json.get("reasons", []))

    profile_result = load_profile(Path(args.profile))
    profile = profile_result["profile"]
    summary["gates"]["profile_status"] = profile_result["status"]
    summary["gates"]["profile_warnings"] = profile_result.get("warnings", [])
    summary["gates"]["profile_errors"] = profile_result.get("errors", [])
    record_step("risk_profile", profile_result["status"], warnings=profile_result.get("warnings", []),
                errors=profile_result.get("errors", []))

    # G8: key market fields must be fresh and independently cross-checked.
    raw_market_data: Dict[str, Any] = {}
    market_validation: Dict[str, Any] = {"status": "NOT_RUN", "errors": ["未提供 --market-data"], "fields": {}}
    if args.market_data:
        try:
            raw_market_data = json.loads(Path(args.market_data).read_text(encoding="utf-8"))
            market_validation = validate_market_data(
                raw_market_data, now=now, allowed_source_ids=verified_source_ids
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            market_validation = {"status": "ERROR", "errors": [f"市场数据文件不可读：{exc}"], "fields": {}}
    market_status = market_validation["status"]
    summary["gates"]["G8_market_data"] = market_status
    summary["gates"]["G8_reasons"] = market_validation.get("errors", [])
    record_step("market_data", market_status, errors=market_validation.get("errors", []))

    points_path = outdir / f"{today}_points.json"
    points = market_data_points(market_validation, raw_market_data) if raw_market_data else []
    write_json(points_path, points)

    # Optional per-ticker evaluation. Required facts are never inferred as passing.
    ticker_results: List[Dict[str, Any]] = []
    ticker_input_status = "PASS"
    tickers: List[Any] = []
    if args.tickers:
        try:
            loaded = json.loads(Path(args.tickers).read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                raise ValueError("tickers 文件顶层必须是 JSON 数组")
            tickers = loaded
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            ticker_input_status = "ERROR"
            summary["gates"]["G6_input_error"] = str(exc)
    # Ticker array order defines priority when available portfolio capacity is scarce.
    reserved_total_pct = 0.0
    reserved_by_sector: Dict[str, float] = {}
    reserved_by_symbol: Dict[str, float] = {}
    portfolio_exposure_baseline: Optional[float] = None
    portfolio_cap_baseline: Optional[float] = None
    sector_exposure_baselines: Dict[str, float] = {}
    stock_exposure_baselines: Dict[str, float] = {}
    for ticker in tickers:
        if not isinstance(ticker, dict):
            ticker_results.append(
                {"final_action": "OBSERVE_ONLY", "status": "ERROR", "blocked_by": ["ticker 必须是对象"]}
            )
            ticker_input_status = "ERROR"
            continue
        flags = ticker.get("flags") if isinstance(ticker.get("flags"), dict) else {}
        try:
            turnover = ticker.get("turnover_20d_avg_yi", ticker.get("turnover_yi"))
            adx = ticker["adx"]
            tech = tech_score(flags, adx, turnover)
            tech_status = "PASS" if not tech["reject"] else "BLOCKED"
        except (KeyError, TypeError, ValueError) as exc:
            tech = {"status": "ERROR", "error": f"技术输入无效：{exc}", "reject": True}
            tech_status = "ERROR"
        grade = tech.get("grade", "")
        position_scale = float(summary["gates"].get("position_scale", 0.0) or 0.0)
        signal_cap = float(tech.get("signal_cap_pct", 0.0) or 0.0) * position_scale
        stock_cap = float(profile.get("single_stock_cap_pct", 0.0) or 0.0)
        risk_cap = float(profile.get("per_trade_risk_pct", 0.0) or 0.0)
        entry_validation = validate_value_sources(
            ticker.get("entry"),
            ticker.get("entry_sources"),
            "entry",
            now,
            verified_source_ids,
        )
        ticker_market_data_ok = market_status == "PASS" and entry_validation["status"] == "PASS"
        proposed = 0.0
        try:
            position_result = evaluate_position(
                {
                    "symbol": ticker.get("symbol", ""),
                    "entry_price": ticker.get("entry"),
                    "stop_price": ticker.get("stop"),
                    "signal_cap_pct": signal_cap,
                    "single_stock_cap_pct": stock_cap,
                    "per_trade_risk_pct": risk_cap,
                    "style": ticker.get("style", ""),
                    "signal_grade": grade,
                    "circuit_breaker_ok": allow_open,
                    "l4_calibrated": ticker.get("l4_calibrated"),
                    "reverse_signal_conflict": ticker.get("reverse_signal_conflict"),
                    "plan_complete": ticker.get("plan_complete"),
                    "market_data_ok": ticker_market_data_ok,
                    "sector_cap_ok": True,
                    "profile_allows_trade": (
                        profile_result["status"] in {"PASS", "DEFAULTED"}
                        and (not ticker.get("is_limit_up_board") or profile.get("allow_limit_up_board") is True)
                        and (ticker.get("style") != "短线" or profile.get("allow_short_line") is True)
                    ),
                }
            )
            proposed = float(position_result.get("position", {}).get("final_position_pct", 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            position_result = {
                "allow_open": False,
                "action": "OBSERVE_ONLY",
                "gate_failures": [f"仓位/门禁输入无效：{exc}"],
                "position": {"ok": False, "reason": str(exc)},
            }
        exposure_errors: List[str] = []
        exposure_input_invalid = False
        for key in (
            "current_stock_exposure_pct",
            "current_sector_exposure_pct",
            "current_total_exposure_pct",
            "total_position_cap_pct",
        ):
            value = ticker.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or value > 100
            ):
                exposure_errors.append(f"{key} 必须是 0 到 100 之间的有限百分比")
                exposure_input_invalid = True
        symbol = ticker.get("symbol")
        sector = ticker.get("sector")
        if not isinstance(symbol, str) or not symbol.strip():
            exposure_errors.append("symbol 必须是非空字符串")
            exposure_input_invalid = True
        if not isinstance(sector, str) or not sector.strip():
            exposure_errors.append("sector 必须是非空字符串，用于累计板块暴露")
            exposure_input_invalid = True

        symbol_key = symbol.strip().casefold() if isinstance(symbol, str) else ""
        sector_key = sector.strip().casefold() if isinstance(sector, str) else ""
        if not exposure_input_invalid:
            total_exposure = float(ticker["current_total_exposure_pct"])
            total_cap = float(ticker["total_position_cap_pct"])
            if portfolio_exposure_baseline is None:
                portfolio_exposure_baseline = total_exposure
                portfolio_cap_baseline = total_cap
            elif (
                total_exposure != portfolio_exposure_baseline
                or total_cap != portfolio_cap_baseline
            ):
                exposure_errors.append("所有候选必须使用一致的当前总仓暴露和总仓上限")
                exposure_input_invalid = True

            sector_exposure = float(ticker["current_sector_exposure_pct"])
            prior_sector_exposure = sector_exposure_baselines.setdefault(
                sector_key, sector_exposure
            )
            if sector_exposure != prior_sector_exposure:
                exposure_errors.append(f"{sector} 候选的当前板块暴露不一致")
                exposure_input_invalid = True

            stock_exposure = float(ticker["current_stock_exposure_pct"])
            prior_stock_exposure = stock_exposure_baselines.setdefault(
                symbol_key, stock_exposure
            )
            if stock_exposure != prior_stock_exposure:
                exposure_errors.append(f"{symbol} 候选的当前单票暴露不一致")
                exposure_input_invalid = True

        if exposure_input_invalid:
            ticker_input_status = "ERROR"
        if not exposure_input_invalid and position_result.get("position", {}).get("ok"):
            if (
                ticker["current_stock_exposure_pct"]
                + reserved_by_symbol.get(symbol_key, 0.0)
                + proposed
                > stock_cap
            ):
                exposure_errors.append("加仓后单票暴露超过风险画像上限")
            sector_cap = float(profile.get("sector_cap_pct", 0.0) or 0.0)
            if (
                ticker["current_sector_exposure_pct"]
                + reserved_by_sector.get(sector_key, 0.0)
                + proposed
                > sector_cap
            ):
                exposure_errors.append("加仓后板块暴露超过风险画像上限")
            if (
                ticker["current_total_exposure_pct"]
                + reserved_total_pct
                + proposed
                > ticker["total_position_cap_pct"]
            ):
                exposure_errors.append("加仓后总仓位超过市场状态仓位闸门")
        position_result["gate_failures"].extend(exposure_errors)
        if entry_validation["status"] != "PASS":
            position_result["gate_failures"].extend(
                f"G4 参考价证据失败：{reason}" for reason in entry_validation["errors"]
            )
        if exposure_errors:
            position_result["allow_open"] = False
            position_result["action"] = "OBSERVE_ONLY"
        if entry_validation["status"] != "PASS":
            position_result["allow_open"] = False
            position_result["action"] = "OBSERVE_ONLY"
        if tech_status != "PASS":
            position_result["allow_open"] = False
            position_result["gate_failures"].append("技术评分未通过流动性/信号等级门槛")
        ticker_allow = (
            position_result.get("allow_open") is True
            and health_status == "PASS"
            and allow_buy
            and breaker_status == "PASS"
            and market_status == "PASS"
            and profile_result["status"] in {"PASS", "DEFAULTED"}
        )
        if ticker_allow:
            reserved_total_pct += proposed
            reserved_by_sector[sector_key] = (
                reserved_by_sector.get(sector_key, 0.0) + proposed
            )
            reserved_by_symbol[symbol_key] = (
                reserved_by_symbol.get(symbol_key, 0.0) + proposed
            )
        blocked_by = list(position_result.get("gate_failures", []))
        if not allow_buy:
            blocked_by.append("G2：当前行情模式不允许买入清单")
        if not allow_open:
            blocked_by.extend(summary["gates"]["G5_reasons"] or ["G5：账户熔断阻断"])
        if market_status != "PASS":
            blocked_by.append("G8：关键市场数据未完整互验")
        ticker_results.append(
            {
                "symbol": ticker.get("symbol"),
                "status": "PASS" if ticker_allow else "BLOCKED",
                "tech": tech,
                "position": position_result,
                "entry_evidence": entry_validation,
                "final_action": "ALLOW_BUY_LIST" if ticker_allow else "OBSERVE_ONLY",
                "blocked_by": blocked_by,
            }
        )
    record_step("tickers", ticker_input_status, n=len(ticker_results))

    # G7 is mandatory for buy-list authorization. No report means NOT_RUN, never pass.
    lint_status = "NOT_RUN"
    lint_result: Dict[str, Any] = {"status": lint_status, "errors": ["未提供报告"]}
    if args.report:
        lint_args = [args.report, "--json"]
        if points_path.exists():
            lint_args += ["--points", str(points_path)]
        lint = run_py("report_lint.py", lint_args)
        lint_result = lint.get("json") if isinstance(lint.get("json"), dict) else {}
        lint_status = str(lint_result.get("status", "ERROR"))
        if lint["returncode"] not in (0, 1) or not lint_result:
            lint_status = "ERROR"
            lint_result = {
                "status": "ERROR",
                "errors": [lint.get("stderr") or lint.get("stdout") or "lint 没有返回有效 JSON"],
            }
    summary["gates"]["G7_report_lint"] = lint_status
    summary["gates"]["G7_errors"] = lint_result.get("errors", [])
    record_step("report_lint", lint_status, errors=lint_result.get("errors", []))

    global_gates = {
        "G1_mode_A": health_status == "PASS" and mode == "A",
        "G5_breaker": breaker_status == "PASS" and allow_open,
        "G7_lint": lint_status == "PASS",
        "G8_market_data": market_status == "PASS",
        "risk_profile": profile_result["status"] in {"PASS", "DEFAULTED"},
        "ticker_input": ticker_input_status == "PASS",
        "G6_at_least_one_allowed_ticker": any(
            ticker.get("final_action") == "ALLOW_BUY_LIST" for ticker in ticker_results
        ),
    }
    global_allow = all(global_gates.values())
    summary["gates"]["global"] = global_gates
    summary["tickers"] = ticker_results
    summary["overall_allow_buy_list"] = global_allow
    summary["overall_status"] = "PASS" if global_allow else "BLOCKED"
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    summary_path = outdir / f"{today}_summary.json"
    write_json(summary_path, summary)
    audit = run_py(
        "audit_write.py",
        [
            "--outdir", args.audit_dir,
            "--date", today,
            "--health", str(health_path),
            "--gates", str(summary_path),
            "--points", str(points_path),
            "--report", args.report or "",
            "--lint", lint_status,
        ],
    )
    audit_ok = audit["returncode"] == 0 and isinstance(audit.get("json"), dict) and audit["json"].get("ok") is True
    record_step("audit_write", "PASS" if audit_ok else "ERROR", result=audit.get("json"), error=audit.get("stderr"))
    if not audit_ok:
        summary["overall_status"] = "ERROR"
        summary["overall_allow_buy_list"] = False
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
