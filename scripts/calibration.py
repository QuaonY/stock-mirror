#!/usr/bin/env python3
"""StockMirror · 情绪阈值月度校准（近60交易日分位）"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List


def percentile(sorted_vals: List[float], p: float) -> float:
    """Nearest-rank style percentile on sorted list; p in 0..100."""
    if not sorted_vals:
        raise ValueError("empty series")
    if p <= 0:
        return float(sorted_vals[0])
    if p >= 100:
        return float(sorted_vals[-1])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def load_rows(path: Path) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"limit_up", "blow_rate", "max_streak", "amount_yi"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise SystemExit(
                f"CSV 必须含列: {sorted(required)}；实际: {reader.fieldnames}"
            )
        for r in reader:
            rows.append(
                {
                    "limit_up": float(r["limit_up"]),
                    "blow_rate": float(r["blow_rate"]),
                    "max_streak": float(r["max_streak"]),
                    "amount_yi": float(r["amount_yi"]),
                }
            )
    return rows


def calibrate(rows: List[Dict[str, float]], window: int = 60) -> Dict:
    if len(rows) < 20:
        sample_note = f"样本仅{len(rows)}日（<20），结果可信度低；建议≥60日"
    elif len(rows) < window:
        sample_note = f"样本{len(rows)}日（<{window}），保留并标注不足"
    else:
        sample_note = f"使用最近{window}日"
        rows = rows[-window:]

    ups = sorted(r["limit_up"] for r in rows)
    blows = sorted(r["blow_rate"] for r in rows)
    streaks = sorted(r["max_streak"] for r in rows)
    amounts = sorted(r["amount_yi"] for r in rows)

    # last 5 amount percentile vs full window for volume climax
    recent5 = amounts[-5:] if len(amounts) >= 5 else amounts
    # For amount, use current mean of last5 vs distribution
    p20_up = percentile(ups, 20)
    p50_up = percentile(ups, 50)
    p80_up = percentile(ups, 80)
    p80_blow = percentile(blows, 80)
    p90_amt = percentile(amounts, 90)
    last5_amt = statistics.mean(r["amount_yi"] for r in rows[-5:]) if rows else 0

    result = {
        "schema": "stock-mirror/calibration@1",
        "calibrated_on": date.today().isoformat(),
        "sample_days": len(rows),
        "sample_note": sample_note,
        "thresholds": {
            "ice_ceiling": {
                "limit_up_lte": round(p20_up, 2),
                "blow_rate_gte": round(p80_blow, 2),
                "max_streak_lte": 2,
            },
            "ferment_floor": {
                "limit_up_gte": round(p50_up, 2),
                "note": "且连板抬升（人工确认）",
            },
            "climax_alarm": {
                "limit_up_gte": round(p80_up, 2),
                "amount_last5_vs_p90": {
                    "last5_avg_yi": round(last5_amt, 2),
                    "p90_amount_yi": round(p90_amt, 2),
                    "hit": last5_amt >= p90_amt,
                },
            },
            "volume_expand": {
                "rule": "当日额 / 20日均额 >= 2.0",
                "amount_p90_yi": round(p90_amt, 2),
            },
        },
        "raw_percentiles": {
            "limit_up_p20": round(p20_up, 2),
            "limit_up_p50": round(p50_up, 2),
            "limit_up_p80": round(p80_up, 2),
            "blow_rate_p80": round(p80_blow, 2),
            "amount_p90": round(p90_amt, 2),
        },
    }
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror sentiment threshold calibration")
    p.add_argument("csv_path", type=Path, help="近60日 CSV：limit_up,blow_rate,max_streak,amount_yi")
    p.add_argument("--out", type=Path, default=Path("state/calibration.json"))
    p.add_argument("--window", type=int, default=60)
    args = p.parse_args()

    rows = load_rows(args.csv_path)
    result = calibrate(rows, args.window)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
