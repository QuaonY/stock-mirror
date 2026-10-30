#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StockMirror 来源证据检查：逐来源样例探活、独立性与模式分类。"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


P0_PATTERNS = {
    "同花顺iFinD": ["ifind", "同花顺", "tonghuashun", "10jqka"],
    "通达信": ["通达信", "tdx", "tdxpy"],
    "东方财富妙想": ["东方财富", "东财", "eastmoney", "妙想", "miaoxiang"],
}
P1_PATTERNS = {
    "万得": ["万得", "wind"],
    "腾讯自选股": ["腾讯自选股", "自选股", "qqstock", "tencent stock"],
    "Tushare": ["tushare"],
}
BACKUP_PATTERNS = {
    "akshare": ["akshare"],
    "雪球": ["雪球", "xueqiu"],
    "choice": ["choice", "东方财富choice"],
    "理杏仁": ["理杏仁"],
}

# 公开网络诊断端点；可达性不替代 MCP 业务拉数或逐来源探活
PROBE_URLS = [
    (
        "eastmoney_sh_index",
        "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f57,f58,f169,f170",
    ),
]


def match_sources(available: List[str]) -> Dict[str, List[str]]:
    joined = [a.lower() for a in available]

    def hits(table: Dict[str, List[str]]) -> List[str]:
        out = []
        for name, kws in table.items():
            if any(k in j for j in joined for k in kws):
                out.append(name)
        return out

    return {
        "p0": hits(P0_PATTERNS),
        "p1": hits(P1_PATTERNS),
        "backup": hits(BACKUP_PATTERNS),
    }


def _source_group(name: str) -> Optional[str]:
    matched = match_sources([name])
    for group in ("p0", "p1", "backup"):
        if matched[group]:
            return group
    return None


def validate_source_evidence(
    raw_sources: Any,
    available: List[str],
    now: Optional[datetime] = None,
    max_age_days: int = 7,
) -> List[Dict[str, Any]]:
    """只接纳逐来源成功且带有效样例时间戳的探活结果。"""
    if not isinstance(raw_sources, list):
        raise ValueError("probe file 必须包含 sources 数组")
    if max_age_days < 0:
        raise ValueError("max_age_days 必须非负")
    now = now or datetime.now(timezone.utc)
    available_set = {name.strip().casefold() for name in available}
    validated: List[Dict[str, Any]] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            validated.append({"ok": False, "reason": "source evidence 必须是对象"})
            continue
        name = str(item.get("name", "")).strip()
        source_id = str(item.get("independent_source_id", "")).strip()
        if not name or not source_id:
            validated.append(
                {"name": name or None, "ok": False, "reason": "缺少 name 或 independent_source_id"}
            )
            continue
        group = _source_group(name)
        if name.casefold() not in available_set or group is None:
            validated.append(
                {"name": name, "ok": False, "reason": "来源未在 --available 中匹配"}
            )
            continue
        if item.get("ok") is not True:
            validated.append(
                {
                    "name": name,
                    "independent_source_id": source_id,
                    "ok": False,
                    "reason": str(item.get("error") or "来源探活失败"),
                }
            )
            continue
        if not str(item.get("sample_field", "")).strip():
            validated.append(
                {
                    "name": name,
                    "independent_source_id": source_id,
                    "ok": False,
                    "reason": "缺少 sample_field",
                }
            )
            continue
        sample_value = item.get("sample_value")
        if (
            isinstance(sample_value, bool)
            or not isinstance(sample_value, (int, float))
            or not math.isfinite(sample_value)
        ):
            validated.append(
                {
                    "name": name,
                    "independent_source_id": source_id,
                    "ok": False,
                    "reason": "缺少非空 sample_value",
                }
            )
            continue
        raw_timestamp = item.get("sample_timestamp")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
            validated.append(
                {
                    "name": name,
                    "independent_source_id": source_id,
                    "ok": False,
                    "reason": "缺少 sample_timestamp",
                }
            )
            continue
        try:
            timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = timestamp.astimezone(timezone.utc)
        except ValueError:
            validated.append(
                {
                    "name": name,
                    "independent_source_id": source_id,
                    "ok": False,
                    "reason": "sample_timestamp 必须是 ISO-8601 时间",
                }
            )
            continue
        age = now.astimezone(timezone.utc) - timestamp
        if age < timedelta(minutes=-5):
            reason = "样例时间戳在未来"
        elif age > timedelta(days=max_age_days):
            reason = f"样例数据超过 {max_age_days} 天"
        else:
            reason = None
        if reason:
            validated.append(
                {
                    "name": name,
                    "independent_source_id": source_id,
                    "ok": False,
                    "sample_timestamp": raw_timestamp,
                    "reason": reason,
                }
            )
            continue
        validated.append(
            {
                "name": name,
                "group": group,
                "independent_source_id": source_id,
                "ok": True,
                "sample_timestamp": timestamp.isoformat(),
                "sample_field": item.get("sample_field"),
                "sample_value": sample_value,
            }
        )
    return validated


def probe_network(timeout: float = 4.0) -> Dict[str, Any]:
    """真探活：能否从公开行情接口取到非空价格字段。"""
    results = []
    ok = False
    sample = None
    for name, url in PROBE_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "StockMirror/1.3.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(body)
            payload = data.get("data") or {}
            price = payload.get("f43")
            if price not in (None, "", "-", 0):
                ok = True
                sample = {
                    "probe": name,
                    "code": payload.get("f57"),
                    "name": payload.get("f58"),
                    "price_raw": price,
                    "change_pct_raw": payload.get("f170"),
                }
                results.append({"probe": name, "ok": True})
                break
            results.append({"probe": name, "ok": False, "reason": "empty price"})
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            results.append({"probe": name, "ok": False, "reason": str(e)[:120]})
    return {"ok": ok, "results": results, "sample": sample}


def load_probe_file(
    path: str, available: List[str], max_age_days: int = 7
) -> Dict[str, Any]:
    """读取逐来源探活结果；只列来源名称的旧格式不构成探活证据。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("probe file 顶层必须是 JSON 对象")
        evidence = validate_source_evidence(
            data.get("sources", []), available, max_age_days=max_age_days
        )
        return {
            "ok": any(row.get("ok") for row in evidence),
            "source_evidence": evidence,
            "from_file": path,
        }
    except (OSError, json.JSONDecodeError, ValueError) as e:
        return {"ok": False, "sources": [], "error": str(e)[:120], "from_file": path}


def decide_mode(
    p0: List[str],
    p1: List[str],
    backup: List[str],
    healthy: bool = True,
    probe_ok: Optional[bool] = None,
    source_evidence: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str, List[str], Dict[str, Any]]:
    """分类来源证据；公开网络探测结果不证明所列 MCP 可用。"""
    tips: List[str] = []
    gates: Dict[str, Any] = {}

    if not healthy:
        mode = "C"
        tips.append("MCP 名称存在但健康检查失败，按模式 C 处理")
        tips.append("请检查 MCP 配置/鉴权，至少保证 2 个可拉数")
        return mode, "N=0（健康失败）", tips, {"probe_ok": probe_ok, "name_match_only": False}

    unique: Dict[str, Dict[str, Any]] = {}
    for row in source_evidence or []:
        if row.get("ok") is True:
            source_id = str(row.get("independent_source_id", "")).strip()
            if source_id:
                unique.setdefault(source_id.casefold(), row)
    evidence = list(unique.values())
    p0_evidence = [row for row in evidence if row.get("group") == "p0"]

    if not evidence:
        mode = "C"
        tips.append("未取得逐来源、带时间戳的样例探活证据；名称匹配或网络可达不计为可用源")
        tips.append("只允许观察池；请用宿主 MCP 拉取样例并提供 --probe-file")
    elif len(evidence) >= 2 and p0_evidence:
        mode = "A"
    elif len(evidence) == 1 and p0_evidence:
        mode = "B"
        tips.append("仅 1 个已验证强行情源，建议再接 1 个独立源互验")
    elif not p0_evidence:
        mode = "C"
        tips.append("已验证来源中没有 P0 行情源，按弱源模式处理")
    else:
        mode = "B"
        tips.append("已验证来源不足 2 个，按单源降级")
    if probe_ok is False:
        tips.append("公开网络探测失败；该结果与 MCP 来源探活分开记录")

    gates = {
        "probe_ok": probe_ok,
        "name_match_only": not bool(evidence),
        "n_verified_independent": len(evidence),
        "n_verified_p0": len(p0_evidence),
        "n_name_matched": len(p0) + len(p1) + len(backup),
    }
    return mode, f"N={len(evidence)}（已验证独立源）", tips, gates


def main() -> int:
    p = argparse.ArgumentParser(description="StockMirror MCP health checker")
    p.add_argument(
        "--available",
        required=True,
        help="逗号分隔的已连接 MCP/工具名，例如: tdx,ifind,eastmoney",
    )
    p.add_argument("--healthy", default="1", help="1=可拉数,0=连接但失败")
    p.add_argument(
        "--probe",
        action="store_true",
        help="网络连通性探测；不作为 MCP 来源可用的证据",
    )
    p.add_argument(
        "--probe-file",
        help="宿主逐来源探活 JSON，sources 项需含 name/independent_source_id/ok/sample_field/sample_value/sample_timestamp",
    )
    p.add_argument("--max-age-days", type=int, default=7)
    p.add_argument("--out", help="将结果写入 JSON 文件")
    args = p.parse_args()

    available = [x.strip() for x in args.available.split(",") if x.strip()]
    healthy = args.healthy not in {"0", "false", "False", "no"}

    probe_detail: Optional[Dict[str, Any]] = None
    probe_ok: Optional[bool] = None
    source_evidence: List[Dict[str, Any]] = []

    if args.probe_file:
        probe_detail = load_probe_file(
            args.probe_file, available, max_age_days=args.max_age_days
        )
        probe_ok = probe_detail.get("ok")
        source_evidence = probe_detail.get("source_evidence", [])
    elif args.probe:
        probe_detail = probe_network()
        probe_ok = bool(probe_detail.get("ok"))

    matched = match_sources(available)
    mode, n_status, tips, gates = decide_mode(
        matched["p0"],
        matched["p1"],
        matched["backup"],
        healthy=healthy,
        probe_ok=probe_ok,
        source_evidence=source_evidence,
    )

    allow_buy_list = mode == "A"
    allow_candidates = mode in {"A", "B"}
    probe_file_error = bool(probe_detail and probe_detail.get("error"))
    health_status = (
        "ERROR"
        if probe_file_error
        else ("PASS" if mode == "A" else ("WARN" if mode == "B" else "BLOCKED"))
    )
    risk_banner = None
    if mode == "C":
        risk_banner = (
            "【数据风险提示】当前未连接足够可用行情数据源或探活失败。"
            "部分数据来自网络公开信息或弱源，可能存在延迟、口径不一致或误差，"
            "结论仅供参考，不作为开仓依据。请连接至少 2 个 MCP 并通过探活。"
        )
    elif mode == "B":
        risk_banner = (
            "【数据源提示】当前仅连接 1 个行情 MCP，关键数字未能完成双源互验，可信度受限。"
        )

    out = {
        "available_input": available,
        "matched": matched,
        "n_status": n_status,
        "mode": mode,
        "status": health_status,
        "allow_candidates": allow_candidates,
        "allow_buy_list": allow_buy_list,
        "risk_banner": risk_banner,
        "tips": tips,
        "gates": gates,
        "probe": probe_detail,
    }
    if probe_file_error:
        out["error"] = probe_detail.get("error")

    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 2 if probe_file_error else 0


if __name__ == "__main__":
    sys.exit(main())
