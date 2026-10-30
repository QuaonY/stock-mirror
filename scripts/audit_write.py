#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 自动审计：把门禁结果与数据点写入 state/audit/YYYY-MM-DD.json (+.md)。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def load_data_points(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("points"), list):
            return data["points"]
    except (UnicodeError, json.JSONDecodeError):
        return []
    return []


def render_md(audit: Dict[str, Any]) -> str:
    mode = audit.get("mode", "")
    n_status = audit.get("n_status", "")
    banner = audit.get("risk_banner") or ""
    points = audit.get("data_points") or []
    gates = audit.get("gates") or {}
    lines = [
        f"# 审计日志 {audit.get('date', '')}",
        "",
        "## 元信息",
        "",
        f"| 项 | 值 |",
        f"|----|----|",
        f"| 生成时间 | {audit.get('generated_at')} |",
        f"| 模式 | {mode} |",
        f"| N | {n_status} |",
        f"| allow_buy_list | {audit.get('allow_buy_list')} |",
        f"| report_lint | {audit.get('report_lint', '未跑')} |",
        f"| 报告文件 | {audit.get('report_path', '【缺失】')} |",
        "",
    ]
    if banner:
        lines += ["> " + banner, ""]
    lines += [
        "## 数据点审计表",
        "",
        "| # | 字段 | 值 | 源1 | 源2 | 一致 | 可信度 | 备注 |",
        "|---|------|----|-----|-----|------|--------|------|",
    ]
    if not points:
        lines.append("| — | — | 【缺失】 | — | — | — | 空 | 未提供 data_points.json |")
    for i, pt in enumerate(points, 1):
        sources = pt.get("sources")
        if isinstance(sources, list):
            source_names = [
                str(
                    source.get("independent_source_id")
                    or source.get("name")
                    or ""
                )
                if isinstance(source, dict)
                else str(source or "")
                for source in sources
            ]
            source1 = source_names[0] if source_names else pt.get("source1", "—")
            source2 = source_names[1] if len(source_names) > 1 else pt.get("source2", "—")
        else:
            source1 = pt.get("source1", "—")
            source2 = pt.get("source2", "—")
        note = pt.get("note", "")
        if pt.get("timestamp"):
            note = f"{note}; timestamp={pt['timestamp']}".strip("; ")
        if pt.get("missing_reason"):
            note = f"{note}; 缺失原因={pt['missing_reason']}".strip("; ")
        lines.append(
            "| {i} | {field} | {value} | {s1} | {s2} | {ok} | {conf} | {note} |".format(
                i=i,
                field=pt.get("field", ""),
                value=pt.get("value", "【缺失】"),
                s1=source1,
                s2=source2,
                ok=pt.get("consistent", "—"),
                conf=pt.get("confidence", "空"),
                note=note,
            )
        )
    lines += ["", "## 门禁结果", ""]
    if gates:
        for k, v in gates.items():
            lines.append(f"- **{k}**: {v}")
    else:
        lines.append("- 【缺失】未提供 gates")
    lines += [
        "",
        "## 签核",
        "",
        "- [ ] 未编造关键行情数字",
        "- [ ] 模式 B/C 风险提示已在报告文首",
        "- [ ] 缺失字段已留空",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror audit writer")
    p.add_argument("--outdir", required=True, help="state/audit")
    p.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天")
    p.add_argument("--health", help="mcp_health 输出 JSON")
    p.add_argument("--breaker", help="circuit_breaker 输出 JSON")
    p.add_argument("--gates", help="run_pipeline 门禁摘要 JSON")
    p.add_argument("--points", help="数据点数组 JSON")
    p.add_argument("--report", help="报告文件路径")
    p.add_argument("--lint", help="PASS/FAIL/未跑")
    args = p.parse_args()

    today = args.date or datetime.now().strftime("%Y-%m-%d")
    health = load_json(args.health)
    breaker = load_json(args.breaker)
    gates_file = load_json(args.gates)
    points = load_data_points(args.points)

    mode = health.get("mode", gates_file.get("mode", ""))
    audit = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "n_status": health.get("n_status", ""),
        "allow_buy_list": health.get("allow_buy_list", gates_file.get("allow_buy_list")),
        "risk_banner": health.get("risk_banner", ""),
        "probe": health.get("probe"),
        "breaker": {
            "allow_new_open": breaker.get("allow_new_open"),
            "position_scale": breaker.get("position_scale"),
            "reasons": breaker.get("reasons"),
        },
        "gates": gates_file.get("gates", gates_file),
        "data_points": points,
        "report_path": args.report,
        "report_lint": args.lint or "未跑",
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / f"{today}.json"
    md_path = outdir / f"{today}.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(audit), encoding="utf-8")
    print(json.dumps({"ok": True, "json": str(json_path), "md": str(md_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
