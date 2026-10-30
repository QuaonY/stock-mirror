#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 技术共振评分：GMMA + 一目均衡（云层/TK）+ ADX + 量能。满分 100。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Dict, List


def tech_score(
    flags: Dict[str, bool], adx: float, turnover_yi: float
) -> Dict[str, Any]:
    """按体系评分表累加。flags 必须显式给出，禁止默认 True。"""
    if not isinstance(flags, dict):
        raise ValueError("flags 必须是对象")
    allowed_flags = {
        "gmma_bull",
        "gmma_dispersion",
        "above_cloud",
        "tenkan_gt_kijun",
        "tk_golden",
        "cloud_thick",
    }
    unknown = set(flags) - allowed_flags
    if unknown:
        raise ValueError(f"未知技术信号：{', '.join(sorted(unknown))}")
    for name, value in flags.items():
        if not isinstance(value, bool):
            raise ValueError(f"技术信号 {name} 必须是布尔值")
    if (
        isinstance(adx, bool)
        or isinstance(turnover_yi, bool)
        or not isinstance(adx, (int, float))
        or not isinstance(turnover_yi, (int, float))
        or not math.isfinite(adx)
        or not math.isfinite(turnover_yi)
    ):
        raise ValueError("ADX and turnover must be finite numbers")
    if adx < 0 or turnover_yi < 0:
        raise ValueError("ADX and turnover must be non-negative")
    parts: List[Dict[str, Any]] = []
    total = 0

    def add(name: str, cond: bool, pts: int) -> None:
        nonlocal total
        if cond:
            total += pts
            parts.append({"item": name, "pts": pts, "hit": True})
        else:
            parts.append({"item": name, "pts": 0, "hit": False})

    add("GMMA多头排列(短>长)", bool(flags.get("gmma_bull")), 25)
    add("GMMA离散度>2%", bool(flags.get("gmma_dispersion")), 10)
    add("价格在云层上方", bool(flags.get("above_cloud")), 20)
    add("转换线>基准线", bool(flags.get("tenkan_gt_kijun")), 10)
    add("TK金叉", bool(flags.get("tk_golden")), 5)
    add("云层厚度>3%", bool(flags.get("cloud_thick")), 5)

    if adx > 40:
        add("ADX>40", True, 20)
    elif adx >= 30:
        add("ADX 30-40", True, 15)
    elif adx >= 20:
        add("ADX 20-30", True, 10)
    else:
        add("ADX<20", False, 0)

    add("成交额>10亿", turnover_yi > 10, 5)

    if total >= 90:
        grade = "S"
        cap = 20.0
    elif total >= 75:
        grade = "A"
        cap = 10.0
    elif total >= 60:
        grade = "B"
        cap = 5.0
    else:
        grade = "C"
        cap = 0.0

    liquidity_ok = turnover_yi >= 1.0  # 硬门槛：20日均额>=1亿
    return {
        "score": total,
        "max_score": 100,
        "grade": grade,
        "signal_cap_pct": cap,
        "liquidity_ok": liquidity_ok,
        "reject": (not liquidity_ok) or grade == "C",
        "parts": parts,
        "note": "参考仓位是上限，实际首仓必须用 position_calc.py 反推",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror tech resonance scorer")
    p.add_argument("--adx", type=float, required=True)
    p.add_argument(
        "--turnover-20d-avg-yi",
        "--turnover-yi",
        type=float,
        required=True,
        dest="turnover_yi",
        help="20 日平均成交额（亿元）；--turnover-yi 为兼容旧名称",
    )
    p.add_argument("--gmma-bull", action="store_true")
    p.add_argument("--gmma-dispersion", action="store_true")
    p.add_argument("--above-cloud", action="store_true")
    p.add_argument("--tenkan-gt-kijun", action="store_true")
    p.add_argument("--tk-golden", action="store_true")
    p.add_argument("--cloud-thick", action="store_true")
    args = p.parse_args()

    flags = {
        "gmma_bull": args.gmma_bull,
        "gmma_dispersion": args.gmma_dispersion,
        "above_cloud": args.above_cloud,
        "tenkan_gt_kijun": args.tenkan_gt_kijun,
        "tk_golden": args.tk_golden,
        "cloud_thick": args.cloud_thick,
    }
    result = tech_score(flags, args.adx, args.turnover_yi)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["reject"] else 1


if __name__ == "__main__":
    sys.exit(main())
