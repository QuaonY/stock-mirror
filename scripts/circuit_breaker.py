#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 账户熔断状态：读写 state/account_state.json，判定是否允许新开仓。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict


DEFAULT_STATE: Dict[str, Any] = {
    "as_of": None,
    "peak_nav": 100.0,
    "current_nav": 100.0,
    "drawdown_pct": 0.0,
    "consecutive_stop_losses": 0,
    "week_pnl_pct": 0.0,
    "month_pnl_pct": 0.0,
    "halt_new_open_until": None,  # ISO date
    "halt_reason": None,
    "position_scale": 1.0,
    "base_position_scale": 1.0,
    "last_reset_month": None,
}


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_STATE)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("账户状态文件顶层必须是 JSON 对象")
    merged = dict(DEFAULT_STATE)
    merged.update(data)
    if "base_position_scale" not in data:
        # Compatibility: preserve the legacy persisted ceiling without reapplying
        # subsequently computed risk reductions on every evaluation.
        merged["base_position_scale"] = data.get("position_scale", 1.0)
    return merged


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def update_and_evaluate(state: Dict[str, Any], today: str) -> Dict[str, Any]:
    """纯评估：不修改输入 state，也不将结果系数反复应用到自身。"""
    state = dict(state)
    try:
        today_date = date.fromisoformat(today)
        if today_date.isoformat() != today:
            raise ValueError
    except ValueError as exc:
        raise ValueError("评估日期必须是 YYYY-MM-DD") from exc
    for key in (
        "peak_nav",
        "current_nav",
        "drawdown_pct",
        "week_pnl_pct",
        "month_pnl_pct",
        "position_scale",
        "base_position_scale",
    ):
        value = state.get(key, DEFAULT_STATE.get(key))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"账户状态字段 {key} 必须是有限数字")
    dd = float(state["drawdown_pct"])
    if not 0 <= dd <= 100:
        raise ValueError("drawdown_pct 必须在 0 到 100 之间")
    if state["peak_nav"] < 0 or state["current_nav"] < 0:
        raise ValueError("净值不能为负数")
    reasons = []
    allow = True
    scale = float(state.get("base_position_scale", 1.0))
    if not 0 <= scale <= 1:
        raise ValueError("base_position_scale 必须在 0 到 1 之间")
    stop_losses = state.get("consecutive_stop_losses", 0)
    if isinstance(stop_losses, bool) or not isinstance(stop_losses, int) or stop_losses < 0:
        raise ValueError("consecutive_stop_losses 必须是非负整数")
    halt_until = state.get("halt_new_open_until")
    if halt_until is not None:
        try:
            halt_date = date.fromisoformat(halt_until)
            if halt_date.isoformat() != halt_until:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("halt_new_open_until 必须是 YYYY-MM-DD 或 null") from exc
    last_reset_month = state.get("last_reset_month")
    if last_reset_month is not None:
        try:
            if len(last_reset_month) != 7 or date.fromisoformat(f"{last_reset_month}-01").strftime("%Y-%m") != last_reset_month:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("last_reset_month 必须是 YYYY-MM 或 null") from exc

    if halt_until and today_date <= halt_date:
        allow = False
        reasons.append(f"熔断保护期至 {state['halt_new_open_until']}")

    if dd >= 12:
        allow = False
        scale = min(scale, 0.0)
        reasons.append("回撤≥12%：停新开仓≥1周")
    elif dd >= 8:
        scale = min(scale, 0.5)
        reasons.append("回撤≥8%：总仓减半；保护期截止日须显式记录")
        if allow and not state.get("halt_new_open_until"):
            allow = False
            reasons.append("需显式设置 halt_new_open_until；脚本不以自然日冒充交易日")

    if state.get("consecutive_stop_losses", 0) >= 3:
        allow = False
        reasons.append("连续3笔止损：当日禁止开仓，需复盘风格错配")

    if state.get("month_pnl_pct", 0.0) <= -10:
        scale = min(scale, 0.3)
        reasons.append("单月亏≥10%：当月剩余总仓≤30%")

    if state.get("week_pnl_pct", 0.0) <= -6:
        scale = min(scale, 0.7)
        reasons.append("单周亏≥6%：下周总仓上限降一档")

    return {
        "allow_new_open": allow,
        "position_scale": round(scale, 4),
        "reasons": reasons or ["正常"],
        "state": state,
        "evaluated_on": today,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror circuit breaker state")
    p.add_argument("--state", required=True, help="state/account_state.json 路径")
    p.add_argument("--nav", type=float, help="更新当前净值")
    p.add_argument("--peak", type=float, help="更新峰值净值")
    p.add_argument("--stop-loss", dest="stop", action="store_true", help="记录一笔止损")
    p.add_argument("--reset-stops", action="store_true", help="清零连续止损")
    p.add_argument("--reset-month", action="store_true", help="确认月度复盘后重置月度亏损/连续止损计数")
    p.add_argument("--week-pnl", type=float)
    p.add_argument("--month-pnl", type=float)
    p.add_argument("--halt-days", type=int, help="设置停新开仓天数（自然日近似）")
    p.add_argument("--halt-until", help="显式设置保护期截止日 YYYY-MM-DD")
    p.add_argument("--base-position-scale", type=float, help="设置基础仓位缩放系数 0..1")
    args = p.parse_args()

    path = Path(args.state)
    try:
        state = load_state(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": f"账户状态不可读：{exc}"}, ensure_ascii=False))
        return 2
    today = date.today().isoformat()

    changed = bool(any(
        value is not None
        for value in (
            args.nav,
            args.peak,
            args.week_pnl,
            args.month_pnl,
            args.base_position_scale,
        )
    ) or args.stop or args.reset_stops or args.reset_month or args.halt_days is not None or args.halt_until)

    if args.reset_month and args.month_pnl is not None:
        p.error("--reset-month 不能与 --month-pnl 同时使用")

    if args.peak is not None:
        if not math.isfinite(args.peak) or args.peak <= 0:
            p.error("--peak 必须为大于 0 的有限数字")
        state["peak_nav"] = args.peak
    if args.nav is not None:
        if not math.isfinite(args.nav) or args.nav <= 0:
            p.error("--nav 必须为大于 0 的有限数字")
        state["current_nav"] = args.nav
        state["peak_nav"] = max(float(state["peak_nav"]), args.nav)
        state["drawdown_pct"] = round(
            (state["peak_nav"] - args.nav) / state["peak_nav"] * 100.0, 4
        )
    if args.stop:
        stop_losses = state.get("consecutive_stop_losses", 0)
        if isinstance(stop_losses, bool) or not isinstance(stop_losses, int) or stop_losses < 0:
            print(json.dumps({"status": "ERROR", "error": "consecutive_stop_losses 必须是非负整数"}, ensure_ascii=False))
            return 2
        state["consecutive_stop_losses"] = stop_losses + 1
    if args.reset_stops:
        state["consecutive_stop_losses"] = 0
    if args.reset_month:
        month = date.today().strftime("%Y-%m")
        if state.get("last_reset_month") == month:
            p.error(f"本月已重置：{month}")
        state["month_pnl_pct"] = 0.0
        state["consecutive_stop_losses"] = 0
        state["last_reset_month"] = month
    if args.week_pnl is not None:
        state["week_pnl_pct"] = args.week_pnl
    if args.month_pnl is not None:
        state["month_pnl_pct"] = args.month_pnl
    if args.base_position_scale is not None:
        if not 0 <= args.base_position_scale <= 1:
            p.error("--base-position-scale 必须在 0 到 1 之间")
        state["base_position_scale"] = args.base_position_scale
    if args.halt_days is not None:
        if args.halt_days <= 0:
            p.error("--halt-days 必须大于 0")
        from datetime import timedelta

        state["halt_new_open_until"] = (
            date.today() + timedelta(days=args.halt_days)
        ).isoformat()
        state["halt_reason"] = f"manual natural-day halt {args.halt_days}d"
    if args.halt_until:
        try:
            halt_date = date.fromisoformat(args.halt_until)
            if halt_date.isoformat() != args.halt_until:
                raise ValueError
        except ValueError:
            p.error("--halt-until 必须是 YYYY-MM-DD")
        state["halt_new_open_until"] = args.halt_until
        state["halt_reason"] = "explicit halt-until date"
    if changed:
        state["as_of"] = today

    try:
        result = update_and_evaluate(state, today)
    except (TypeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    result["status"] = "PASS" if result["allow_new_open"] else "BLOCKED"
    if changed:
        try:
            save_state(path, state)
        except OSError as exc:
            print(json.dumps({"status": "ERROR", "error": f"账户状态不可写：{exc}"}, ensure_ascii=False))
            return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["allow_new_open"] else 1


if __name__ == "__main__":
    sys.exit(main())
