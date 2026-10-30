#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 报告规范校验：检查 HTML/Markdown 复盘是否缺模块、缺来源、缺留空标注。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REQUIRED_BLOCKS = [
    ("数据源状态", [r"数据源状态", r"数据风险提示"]),
    ("元信息", [r"元信息", r"数据可信度"]),
    ("宏观", [r"宏观", r"消息"]),
    ("大盘", [r"大盘", r"指数"]),
    ("板块", [r"板块", r"资金"]),
    ("个股", [r"个股", r"技术"]),
    ("心态", [r"心态", r"纪律"]),
    ("策略", [r"策略", r"明日", r"作战单"]),
    ("五维总结", [r"五维", r"整体市场"]),
    ("免责", [r"不构成", r"投资建议", r"免责"]),
]

SOURCE_RE = re.compile(r"来源[:：]")
MISS_RE = re.compile(r"【缺失】")
FAKE_HINTS = re.compile(r"(大概|约|估计|应该是|好像是)\s*\d")


def lint_text(text: str) -> Tuple[List[str], List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    notes: List[str] = []

    for name, pats in REQUIRED_BLOCKS:
        if not any(re.search(p, text) for p in pats):
            errors.append(f"缺少必备模块：{name}")

    has_source = bool(SOURCE_RE.search(text))
    has_miss = bool(MISS_RE.search(text))
    digits = len(re.findall(r"\d+(?:\.\d+)?", text))

    if digits >= 15 and not has_source:
        errors.append("出现较多数字但未见「来源：」标注，违反来源强制规则")

    if FAKE_HINTS.search(text):
        warnings.append("疑似模糊估算表述（大概/约/估计+数字），关键行情禁止")

    if re.search(r"北向.*净流入\s*[-+]?\d+", text) and "实时数据不可得" not in text:
        warnings.append("疑似旧口径北向净流入数字，请确认是否为规则变更前数据")

    if re.search(r"买入清单", text) and re.search(r"模式\s*[：:]?\s*C|网络弱源", text):
        errors.append("模式 C（网络弱源）禁止输出买入清单，仅允许观察池")

    if not has_miss and re.search(r"冲突/缺失|冲突", text):
        notes.append("有冲突提及但未用【缺失】模板，建议统一留空格式")

    notes.append(f"数字约 {digits} 处；来源标注={'有' if has_source else '无'}；缺失标注={'有' if has_miss else '无'}")
    return errors, warnings, notes


class ReportTextParser(HTMLParser):
    """提取 HTML 可见文本，避免正则剥标签误读属性与脚本内容。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "head"}:
            self.hidden_depth += 1
        elif tag.lower() in {"p", "div", "section", "article", "tr", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "head"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag.lower() in {"p", "div", "section", "article", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def visible_text(text: str, path: Path) -> str:
    if path.suffix.lower() not in {".html", ".htm"}:
        return text
    parser = ReportTextParser()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def lint_data_points(path: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"数据点文件不可读：{exc}"], warnings
    points = data if isinstance(data, list) else data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        return ["数据点文件必须是数组或包含 points 数组的对象"], warnings
    for index, point in enumerate(points, 1):
        if not isinstance(point, dict):
            errors.append(f"数据点 #{index} 必须是对象")
            continue
        field = point.get("field")
        if not field:
            errors.append(f"数据点 #{index} 缺少 field")
        value = point.get("value")
        if value in (None, "", "【缺失】"):
            if not point.get("missing_reason"):
                errors.append(f"数据点 #{index} 缺值且缺少 missing_reason")
            continue
        sources = point.get("sources")
        if sources is None:
            sources = [point.get("source1"), point.get("source2")]
        source_ids = {
            str(source.get("independent_source_id") or source.get("name") or "").strip().casefold()
            if isinstance(source, dict)
            else str(source or "").strip().casefold()
            for source in sources
            if not isinstance(source, dict) or source.get("ok") is True
        } if isinstance(sources, list) else set()
        source_ids.discard("")
        if not source_ids:
            errors.append(f"数据点 #{index}（{field or '未命名'}）没有来源")
        confidence = str(point.get("confidence", "")).lower()
        if confidence in {"高", "high"} and len(source_ids) < 2:
            errors.append(f"数据点 #{index} 标为高可信但不足两个独立来源")
        if not point.get("date") and not point.get("timestamp"):
            warnings.append(f"数据点 #{index} 缺少日期/时间戳")
    return errors, warnings


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror report linter")
    p.add_argument("path", help="HTML 或 Markdown 报告路径")
    p.add_argument("--points", help="可选数据点 JSON，检查来源/时间/缺失原因")
    p.add_argument("--json", action="store_true", help="输出机器可读 JSON 状态")
    args = p.parse_args()
    path = Path(args.path)
    if not path.exists():
        result = {"status": "ERROR", "errors": [f"file not found: {path}"], "warnings": [], "notes": []}
        print(json.dumps(result, ensure_ascii=False) if args.json else f"ERROR: file not found: {path}")
        return 2
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        result = {"status": "ERROR", "errors": [f"cannot read report: {exc}"], "warnings": [], "notes": []}
        print(json.dumps(result, ensure_ascii=False) if args.json else result["errors"][0])
        return 2
    plain = visible_text(text, path)
    errors, warnings, notes = lint_text(plain)
    if args.points:
        point_errors, point_warnings = lint_data_points(Path(args.points))
        errors.extend(point_errors)
        warnings.extend(point_warnings)
    status = "FAIL" if errors else "PASS"

    if args.json:
        print(json.dumps(
            {"status": status, "errors": errors, "warnings": warnings, "notes": notes,
             "scope": "structural and supplied data-point checks; not proof of market-data truth"},
            ensure_ascii=False,
            indent=2,
        ))
        return 0 if status == "PASS" else 1
    print(f"# StockMirror Lint: {path.name}")
    if errors:
        print("\n## ERROR")
        for e in errors:
            print(f"- {e}")
    if warnings:
        print("\n## WARNING")
        for w in warnings:
            print(f"- {w}")
    print("\n## NOTE")
    for n in notes:
        print(f"- {n}")

    print(f"\nRESULT: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
