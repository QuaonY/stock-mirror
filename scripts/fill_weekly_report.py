#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从台账 + 熔断状态生成周度复盘 Markdown 填空块。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _truthy(v: Any) -> bool:
    return str(v).lower() in {"true", "1", "yes", "y"}


def filter_rows(rows: List[Dict[str, str]], start: Optional[str], end: Optional[str]) -> List[Dict[str, str]]:
    if not start and not end:
        return rows
    out = []
    for r in rows:
        d = r.get("close_date") or r.get("open_date") or ""
        if start and d and d < start:
            continue
        if end and d and d > end:
            continue
        out.append(r)
    return out


def summarize(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0, "note": "本周无平仓样本"}
    nets = [_f(r.get("net_pnl_pct")) for r in rows]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    win_rate = len(wins) / n * 100.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 1e-9 else None
    discipline = sum(1 for r in rows if _truthy(r.get("discipline_ok")))
    stop_hits = sum(1 for r in rows if _truthy(r.get("stop_hit")))
    no_fill = sum(1 for r in rows if _truthy(r.get("limit_locked_no_fill")))
    max_loss = min(nets) if nets else 0.0
    return {
        "n": n,
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "payoff_ratio": round(payoff, 2) if payoff is not None else None,
        "net_sum_pct": round(sum(nets), 2),
        "max_loss_pct": round(max_loss, 2),
        "discipline_rate_pct": round(discipline / n * 100.0, 2),
        "stop_hit_n": stop_hits,
        "limit_locked_no_fill_n": no_fill,
        "sample_warning": "样本<20，不下「策略无效」结论" if n < 20 else "",
    }


def load_state(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def render_markdown(
    start: str,
    end: str,
    stats: Dict[str, Any],
    state: Dict[str, Any],
    benchmark: str = "沪深300",
    benchmark_change: Optional[float] = None,
) -> str:
    scale = state.get("position_scale")
    dd = state.get("drawdown_pct")
    allow = "保护期" if state.get("halt_new_open_until") else "正常"
    if stats.get("n", 0) == 0:
        perf_rows = (
            f"| 交易笔数 | 0 | {stats.get('note','')} |\n"
            f"| 胜率 | — | 无样本 |\n"
            f"| 盈亏比 | — | 无样本 |\n"
            f"| 最大单笔亏损 | — | 无样本 |\n"
            f"| 止损执行率 | — | 无样本 |\n"
            f"| 净收益（扣成本） | 0.00% | 无样本 |\n"
            f"| 基准涨跌 | {'【缺失】' if benchmark_change is None else f'{benchmark_change:.2f}%'} | {benchmark} |\n"
            f"| 超额 | — | 无样本 |\n"
        )
    else:
        excess = (
            None
            if benchmark_change is None
            else stats["net_sum_pct"] - benchmark_change
        )
        perf_rows = (
            f"| 交易笔数 | {stats['n']} | |\n"
            f"| 胜率 | {stats['win_rate_pct']}% | |\n"
            f"| 盈亏比 | {stats['payoff_ratio'] if stats['payoff_ratio'] is not None else '—'} | avg_win/avg_loss |\n"
            f"| 最大单笔亏损 | {stats['max_loss_pct']}% | |\n"
            f"| 止损执行率 | {stats['discipline_rate_pct']}% | 目标 ≥80%（纪律率） |\n"
            f"| 净收益（扣成本） | {stats['net_sum_pct']}% | 台账合计 |\n"
            f"| 基准涨跌 | {'【缺失】' if benchmark_change is None else f'{benchmark_change:.2f}%'} | {benchmark} |\n"
            f"| 超额 | {'【缺失】' if excess is None else f'{excess:.2f}%'} | |\n"
        )

    warn = stats.get("sample_warning") or ""
    stop_n = stats.get("stop_hit_n", 0)
    no_fill = stats.get("limit_locked_no_fill_n", 0)

    return f"""## 【自动填空】周度绩效（来自台账）

> 生成日：{date.today().isoformat()} · 周期：{start} ~ {end}
> 运行：`python scripts/fill_weekly_report.py --ledger state/trade-ledger.csv --start {start} --end {end} --state state/account_state.json`

| 项 | 值 |
|----|----|
| 账户熔断状态 | {allow} |
| 峰值回撤 | {'【缺失】' if dd is None else f'{dd}%'} |
| 仓位缩放系数 | {'【缺失】' if scale is None else scale} |
| 本周止损笔数 | {stop_n} |
| 一字/无法成交止损 | {no_fill} |

### 绩效表（可直接粘贴入周复盘）

| 指标 | 本周 | 备注 |
|------|------|------|
{perf_rows}

- [ ] 请人工补充：计划纪律、主线对错、核心池调整、下周风格
- 提示：{warn or '若纪律率<80%，先修纪律再修策略'}
"""


def main() -> int:
    p = argparse.ArgumentParser(description="Fill weekly review from trade ledger")
    p.add_argument("--ledger", required=True, help="trade-ledger.csv")
    p.add_argument("--state", help="account_state.json")
    p.add_argument("--start", help="YYYY-MM-DD，默认本周一")
    p.add_argument("--end", help="YYYY-MM-DD，默认今天")
    p.add_argument("--benchmark", default="沪深300")
    p.add_argument("--benchmark-change", type=float, dest="bmk")
    p.add_argument("--out", help="输出 md 路径，默认打印")
    args = p.parse_args()

    today = date.today()
    start = args.start or (today - timedelta(days=today.weekday())).isoformat()
    end = args.end or today.isoformat()

    path = Path(args.ledger)
    if not path.exists():
        print(json.dumps({"error": f"ledger not found: {path}"}, ensure_ascii=False))
        return 2
    with path.open("r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rows = filter_rows(rows, start, end)
    stats = summarize(rows)
    state = load_state(Path(args.state) if args.state else None)
    md = render_markdown(start, end, stats, state, args.benchmark, args.bmk)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
