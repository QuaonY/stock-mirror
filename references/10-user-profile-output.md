# 10 · 用户画像与输出粒度

修复「适用性」缺陷：避免一刀切仓位与过重报告。

## 10.1 用户风险画像

文件：`state/user_risk_profile.json`（schema 见同目录）

| 字段 | 作用 |
|------|------|
| risk_level | 保守/稳健/积极 → 默认总仓位闸门上下限收紧系数 |
| per_trade_risk_pct | 代入仓位公式 |
| single_stock_cap_pct | 单票上限 |
| allow_limit_up_board | false 则禁止打板策略与一字板接力 |
| preferred_style | 默认工作流 |
| output_mode | full / summary / plan-only |
| benchmark | 绩效对比基准 |

**画像缺失时**：按「稳健 + 禁止打板 + full 输出」执行，并在报告提示「未提供风险画像，使用默认」。

## 10.2 输出粒度

| 模式 | 内容 | 何时用 |
|------|------|--------|
| **full** | HTML 完整六步 + 表 + 审计提示 | 每日收盘复盘（默认） |
| **summary** | 数据源状态 + 五维 KPI + 主线 + 3 条要点 | 快速扫一眼 |
| **plan-only** | 仅盘前作战单 + 门禁结果 | 盘前 5 分钟 |

summary/plan-only **不能省略**：数据源状态、熔断、缺失标注、免责。

## 10.3 轻量模式禁止缩水的项

- 来源标注
- 【缺失】留空
- 熔断/模式门禁
- 反向情景（若给出买入/持有建议）
