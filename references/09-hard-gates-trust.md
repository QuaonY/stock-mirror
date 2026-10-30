# 09 · 硬门禁与 Trust 协议（可机器核验）

本节修复「有效性/可信任度」缺陷：把口头规则变成**可执行卡点**。

## 9.1 硬门禁矩阵（Fail-Fast）

| # | 门禁 | 判定 | 强制动作 |
|---|------|------|----------|
| G1 | MCP 健康 | `scripts/mcp_health.py` 输出 mode | 写入报告文首 |
| G2 | 模式 C 禁买 | mode=C | **禁止买入清单**；只允许观察池 + 风险提示 |
| G3 | 模式 B 限权 | mode=B | 仅可列候选/观察，不形成开仓许可；补足独立来源后再评估 |
| G4 | 数据冲突 | 价差≥0.1% 或方向相反且无第三源仲裁 | 该票/指数降为观察，不进买入清单 |
| G5 | 账户熔断 | `scripts/circuit_breaker.py` allow=false | 禁止新开仓（S 级也不行） |
| G6 | 开仓五条件 | `scripts/position_calc.py` allow_open=false | 仅进观察池，输出 gate_failures |
| G7 | 报告规范 | 状态不是明确 `PASS` | `FAIL/ERROR/NOT_RUN` 均阻断整体许可 |
| G8 | 关键字段 | 指数收盘/成交额/涨停数缺失、过期或不足双源 | 只允许方向参考/观察，不允许开仓 |

**执行顺序建议**：

```
mcp_health(逐来源证据) → 取数/互验 → circuit_breaker(只读评估)
→ G8市场数据校验 → (逐票) tech_score + 五条件 + position_calc
→ 生成报告 → report_lint(PASS) → 写 audit-log
```

## 9.2 Trust 协议（每条数据）

### 9.2.1 取数步骤表（禁止只写结论）

| 字段 | 主源 | 备源 | 必填 | 失败时 |
|------|------|------|------|--------|
| 指数收盘 OHLC | MCP行情 | 网络证券媒体 | 是 | `【缺失】` |
| 两市成交额 | MCP | 网络 | 是 | `【缺失】` |
| 涨停/跌停/连板/炸板 | MCP/涨停工具 | 网络 | 是 | `【缺失】` |
| 主力净流入 | 东财系/同花顺 | 万得 | 是 | 标口径缺失 |
| 宏观消息 | 官网/财联社 | 研报 | 是 | 「据报道」 |

### 9.2.2 互验字段白名单（必须双源）

- 上证/深证/创业板 收盘涨跌幅
- 两市成交额
- 涨停家数、跌停家数、最高连板
- 买入清单中每只票的参考价（区间中值）

### 9.2.3 审计日志

每次复盘必须生成 @../templates/audit-log.md 一份，与报告同日归档。

## 9.3 禁止项（机器可 grep）

- 买入清单 + 模式 C 同现
- 「大概/约/估计」+ 行情数字
- 无「来源：」却有多处数字结论
- 北向净流入具体数字且无「规则变更/不可得」说明

## 9.4 MCP 健康检查标准

「已连接」≠「可用」。判定可用需同时满足：

1. 名称匹配成功（见 01 §1.0.1）
2. 能完成一次**样例拉取**（例如任一指数当日涨跌幅）且非空
3. 时间戳为最近交易日或明确标注延迟

不满足 → 从 N 中扣除，按降级模式处理。

`--probe` 只测试公开网络端点是否可达，不计入行情 MCP 的 N。宿主探活文件示例：

```json
{
  "sources": [
    {
      "name": "tdx",
      "independent_source_id": "tdx",
      "ok": true,
      "sample_field": "index_change_pct",
      "sample_value": 0.12,
      "sample_timestamp": "REPLACE_WITH_CURRENT_ISO8601_TIMESTAMP"
    },
    {
      "name": "ifind",
      "independent_source_id": "ifind",
      "ok": true,
      "sample_field": "index_change_pct",
      "sample_value": 0.12,
      "sample_timestamp": "REPLACE_WITH_CURRENT_ISO8601_TIMESTAMP"
    }
  ]
}
```

默认拒绝超过 7 天或未来时间戳；宿主应按最近交易日拉取，不要用旧数据冒充当日数据。

## 9.5 G8 市场数据文件格式

`run_pipeline.py --market-data` 要求 JSON 对象至少包含 `index_close`、`turnover`、`limit_up_count` 三个字段。每项格式如下：

```json
{
  "value": 3250.12,
  "timestamp": "REPLACE_WITH_CURRENT_ISO8601_TIMESTAMP",
  "sources": [
    {
      "independent_source_id": "tdx",
      "ok": true,
      "value": 3250.12,
      "timestamp": "REPLACE_WITH_CURRENT_ISO8601_TIMESTAMP"
    },
    {
      "independent_source_id": "ifind",
      "ok": true,
      "value": 3250.10,
      "timestamp": "REPLACE_WITH_CURRENT_ISO8601_TIMESTAMP"
    }
  ]
}
```

每个来源还必须提供自己的原始值与时间戳；示例中的来源和值必须替换为真实的成功拉取结果，且占位时间戳须换成实际拉取时间。指数收盘和买入参考价差异须小于 0.1%，成交额差异须小于 1%，涨停数须完全一致。三个字段都必须是有限非负数字、时间戳有效且不超过 7 天，并有至少两个不同的 `independent_source_id`；否则 G8/G4 不通过。此校验核对输入结构和证据数量，不代表脚本能够独立证明来源数据真实。

逐票输入还必须提供数值型 `entry`、`entry_sources` 原始报价和时间戳、非空 `sector`；报价差异达到 0.1% 即阻断该票，不能用单一汇总价替代互验。多票组合按 tickers 数组顺序分配剩余仓位，逐项累计单票、板块和总仓预算；所有候选必须提供一致的当前总仓暴露与总仓上限，同一股票/板块的当前暴露也须一致。

## 9.6 机器门禁状态

机器状态使用 `PASS`、`BLOCKED`、`WARN`、`ERROR`、`NOT_RUN`。整体开仓许可仅在所有必需全局门禁明确通过时为真；未运行和执行错误均 fail-closed。模式 B 可生成候选观察结果，但不允许产生开仓许可。报告 lint 是结构/数据点完整性检查，不是行情真实性证明。

账户熔断脚本默认只读评估。只有显式传入净值、盈亏、止损或保护期更新参数时才写回账户状态；单纯流水线评估不会修改状态文件。8% 回撤后的保护期截止日必须显式记录，脚本不将自然日冒充交易日。
