#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 仓位计算：止损距离 + 首仓% + 开仓五条件门禁。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple


def stop_distance_pct(entry: float, stop: float) -> float:
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in (entry, stop)
    ) or not all(math.isfinite(value) for value in (entry, stop)):
        raise ValueError("entry and stop must be finite numbers")
    if entry <= 0:
        raise ValueError("entry must be > 0")
    return (entry - stop) / entry * 100.0


def position_pct(
    entry: float,
    stop: float,
    signal_cap_pct: float,
    single_stock_cap_pct: float,
    per_trade_risk_pct: float,
    max_stop_distance_pct: float = 12.0,
) -> Dict[str, Any]:
    """首仓% = min(信号参考仓, 单票上限, 单笔风险上限/止损距离%)。"""
    values = (
        entry,
        stop,
        signal_cap_pct,
        single_stock_cap_pct,
        per_trade_risk_pct,
        max_stop_distance_pct,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ) or not all(math.isfinite(value) for value in values):
        raise ValueError("所有价格和仓位参数必须是有限数值")
    dist = stop_distance_pct(entry, stop)
    if dist <= 0:
        return {
            "ok": False,
            "reason": "止损价必须低于买入价",
            "stop_distance_pct": dist,
        }
    if signal_cap_pct < 0 or single_stock_cap_pct <= 0 or per_trade_risk_pct <= 0:
        raise ValueError("信号仓位不得为负，单票上限和单笔风险上限必须大于 0")
    if max_stop_distance_pct <= 0:
        raise ValueError("止损距离上限必须大于 0")
    if dist > max_stop_distance_pct:
        return {
            "ok": False,
            "reason": f"止损距离 {dist:.2f}% 超过上限 {max_stop_distance_pct}%，放弃或等更好买点",
            "stop_distance_pct": dist,
        }
    risk_based = per_trade_risk_pct / (dist / 100.0)
    final = min(signal_cap_pct, single_stock_cap_pct, risk_based)
    return {
        "ok": True,
        "stop_distance_pct": round(dist, 4),
        "signal_cap_pct": signal_cap_pct,
        "single_stock_cap_pct": single_stock_cap_pct,
        "risk_based_pct": round(risk_based, 4),
        "final_position_pct": round(final, 4),
        "formula": "min(signal_cap, stock_cap, risk_cap/stop_distance)",
    }


def check_open_gates(
    circuit_breaker_ok: Optional[bool],
    style: str,
    l4_calibrated: Optional[bool],
    signal_grade: str,
    reverse_signal_conflict: Optional[bool],
    position: Dict[str, Any],
    plan_complete: Optional[bool],
    market_data_ok: Optional[bool] = None,
    sector_cap_ok: Optional[bool] = None,
    profile_allows_trade: Optional[bool] = None,
) -> Tuple[bool, List[str]]:
    """逐项验证开仓条件和市场/适用性门禁；未提供证据按失败处理。"""
    fails: List[str] = []
    if circuit_breaker_ok is not True:
        fails.append("条件1失败：账户熔断未解除或未核验")
    if style not in {"短线", "波段", "长线"}:
        fails.append("条件2失败：风格未明确（短线/波段/长线）")
    elif l4_calibrated is not True:
        fails.append("条件2失败：L4 未按该风格校准")
    if signal_grade not in {"S", "A", "B"}:
        fails.append("条件3失败：技术信号 < B 或缺失")
    if reverse_signal_conflict is None:
        fails.append("条件3失败：反向信号冲突状态未核验")
    elif reverse_signal_conflict:
        fails.append("条件3失败：趋势类与反转类信号并存")
    if not position.get("ok"):
        fails.append(f"条件4失败：{position.get('reason')}")
    if plan_complete is not True:
        fails.append("条件5失败：盘前清单不完整（止损/加仓/止盈/最差情景/证伪）")
    if market_data_ok is not True:
        fails.append("G8 失败：关键市场数据未完整互验")
    if sector_cap_ok is not True:
        fails.append("组合门禁失败：单票/板块暴露未核验或超过上限")
    if profile_allows_trade is not True:
        fails.append("适用性门禁失败：风险画像未核验或不允许该交易")
    return (len(fails) == 0), fails


def evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    missing_prices = [
        key for key in ("entry_price", "stop_price")
        if key not in payload or payload[key] is None
    ]
    if missing_prices:
        raise ValueError(f"缺少必需价格字段：{', '.join(missing_prices)}")

    def number(key: str, default: Optional[float] = None) -> float:
        value = payload.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} 必须是数值")
        return float(value)

    entry = number("entry_price")
    stop = number("stop_price")
    pos = position_pct(
        entry=entry,
        stop=stop,
        signal_cap_pct=number("signal_cap_pct", 10.0),
        single_stock_cap_pct=number("single_stock_cap_pct", 15.0),
        per_trade_risk_pct=number("per_trade_risk_pct", 1.0),
        max_stop_distance_pct=number("max_stop_distance_pct", 12.0),
    )
    open_ok, fails = check_open_gates(
        circuit_breaker_ok=payload.get("circuit_breaker_ok"),
        style=str(payload.get("style", "")),
        l4_calibrated=payload.get("l4_calibrated"),
        signal_grade=str(payload.get("signal_grade", "")),
        reverse_signal_conflict=payload.get("reverse_signal_conflict"),
        position=pos,
        plan_complete=payload.get("plan_complete"),
        market_data_ok=payload.get("market_data_ok"),
        sector_cap_ok=payload.get("sector_cap_ok"),
        profile_allows_trade=payload.get("profile_allows_trade"),
    )
    return {
        "symbol": payload.get("symbol", ""),
        "position": pos,
        "allow_open": open_ok,
        "gate_failures": fails,
        "action": "ALLOW_BUY_LIST" if open_ok else "OBSERVE_ONLY",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror position & open-gate calculator")
    p.add_argument("--entry", type=float, help="买入价")
    p.add_argument("--stop", type=float, help="止损价")
    p.add_argument("--signal-cap", type=float, default=10.0, dest="signal_cap")
    p.add_argument("--stock-cap", type=float, default=15.0, dest="stock_cap")
    p.add_argument("--risk-cap", type=float, default=1.0, dest="risk_cap")
    p.add_argument("--style", default="", help="短线/波段/长线")
    p.add_argument("--grade", default="", dest="signal_grade", help="S/A/B/C")
    p.add_argument("--circuit-breaker-ok", action="store_true")
    p.add_argument("--l4-calibrated", action="store_true")
    reverse = p.add_mutually_exclusive_group()
    reverse.add_argument("--reverse-signal-clear", action="store_true")
    reverse.add_argument("--reverse-signal-conflict", action="store_true")
    p.add_argument("--plan-complete", action="store_true")
    p.add_argument("--market-data-ok", action="store_true")
    p.add_argument("--sector-cap-ok", action="store_true")
    p.add_argument("--profile-allows-trade", action="store_true")
    p.add_argument("--json", dest="json_path", help="从 JSON 文件读取（优先）")
    args = p.parse_args()

    if args.json_path:
        with open(args.json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif args.entry is not None and args.stop is not None:
        payload = {
            "entry_price": args.entry,
            "stop_price": args.stop,
            "signal_cap_pct": args.signal_cap,
            "single_stock_cap_pct": args.stock_cap,
            "per_trade_risk_pct": args.risk_cap,
            "style": args.style,
            "signal_grade": args.signal_grade,
            "circuit_breaker_ok": args.circuit_breaker_ok,
            "l4_calibrated": args.l4_calibrated,
            "plan_complete": args.plan_complete,
            "market_data_ok": args.market_data_ok,
            "sector_cap_ok": args.sector_cap_ok,
            "profile_allows_trade": args.profile_allows_trade,
        }
        if args.reverse_signal_clear:
            payload["reverse_signal_conflict"] = False
        elif args.reverse_signal_conflict:
            payload["reverse_signal_conflict"] = True
    else:
        p.print_help()
        return 2

    try:
        result = evaluate(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("allow_open") else 1


if __name__ == "__main__":
    sys.exit(main())
