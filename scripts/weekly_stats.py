#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周度绩效：从 trade-ledger.csv 汇总胜率/盈亏比/止损执行率。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def summarize(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0, "note": "样本不足，不下策略结论"}
    nets = [float(r.get("net_pnl_pct") or 0) for r in rows]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    win_rate = len(wins) / n * 100.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 1e-9 else None
    discipline = sum(1 for r in rows if str(r.get("discipline_ok", "")).lower() in {"true", "1", "yes"})
    stop_hits = sum(1 for r in rows if str(r.get("stop_hit", "")).lower() in {"true", "1", "yes"})
    no_fill = sum(1 for r in rows if str(r.get("limit_locked_no_fill", "")).lower() in {"true", "1", "yes"})
    return {
        "n": n,
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "payoff_ratio": round(payoff, 2) if payoff is not None else None,
        "net_sum_pct": round(sum(nets), 2),
        "discipline_rate_pct": round(discipline / n * 100.0, 2),
        "stop_hit_n": stop_hits,
        "limit_locked_no_fill_n": no_fill,
        "sample_warning": "样本<20 时不下「策略无效」结论" if n < 20 else "",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror weekly performance")
    p.add_argument("csv_path", help="trade-ledger.csv")
    args = p.parse_args()
    path = Path(args.csv_path)
    if not path.exists():
        print(json.dumps({"error": "file not found"}, ensure_ascii=False))
        return 2
    with path.open("r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
