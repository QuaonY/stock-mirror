---
name: "stock-mirror"
display_name: "StockMirror · 股海镜鉴"
display_name_en: "StockMirror"
description: "StockMirror（股海镜鉴）A股每日分析→复盘→规划→选股作战手册。覆盖数据基建互验、六步复盘SOP、选股漏斗、短线/波段/长线工作流、仓位公式与账户熔断。Use when the user asks for 复盘、盘前、选股、资金流、连板、情绪周期、止损、仓位、DCF、护城河、技术诊断, or to draft a trade plan. 不构成投资建议。"
description_zh: "StockMirror（股海镜鉴）A股每日分析→复盘→规划→选股作战手册。覆盖数据基建互验、六步复盘SOP、选股漏斗、短线/波段/长线工作流、仓位公式与账户熔断。触发词：复盘、盘前、选股、资金流、连板、情绪周期、止损、仓位、DCF、护城河、技术诊断。"
description_en: "StockMirror. Unified A-share daily analysis, review, planning, and stock-selection playbook. Covers multi-source data validation, 6-step review SOP, selection funnel, short/swing/long workflows, position sizing and account circuit breakers. Use for daily review, pre-market plan, stock screening, capital flow, limit-up boards, sentiment cycle, stop-loss, position sizing, DCF, moat, technical diagnosis. Not investment advice."
category: "finance"
version: "1.3.0"
author: "Quaon"
allowed-tools: "Read, Write, Edit, Glob, Grep, Bash, WebFetch, WebSearch, Skill"
---

# StockMirror · 股海镜鉴

> Stock = 股，Mirror = 镜鉴。以市场为镜，鉴往知来。

## 定位与红线

可每日执行、可周期切换（短线/波段/长线）、可工具落地的统一作战手册。

**红线（每次执行必读）**：
1. 本技能是**分析框架**，不构成任何投资建议。
2. 数据缺失如实标注，**绝不编造**；关键数字 ≥2 源一致才标「高可信」。
3. 关键决策点多源交叉验证；源间冲突未解决时标「低」，该票/该指数降为观察。
4. **账户熔断优先于一切信号**——触发熔断时，再强的 S 级信号也不新开仓。
5. 买入有清单，卖出有纪律——计划外不开仓；开仓必须过五条件 + 仓位公式。

---

## 何时触发本技能

| 用户意图 | 动作入口 |
|----------|----------|
| 今日/昨日复盘、盘前规划 | → [每日闭环](#每日闭环六步-sop) |
| 选股、筛票、找主线 | → [选股漏斗](#选股漏斗) |
| 短线/波段/长线怎么做 | → [三条工作流](#三条工作流) |
| 止损、仓位、回撤、熔断 | → [仓位与风控](#仓位与风控) |
| ROE/DCF/护城河/安全边际 | → @references/05-risk-control.md + @references/07-thresholds.md |
| GMMA/一目均衡/ADX/技术分 | → @references/04-workflows.md + @references/07-thresholds.md |
| 模板填写（盘前单/周复盘） | → @templates/ |

详细规则一律读对应 reference，不要凭记忆硬答。

---

## 使用原则（不可颠倒）

1. **先定大势 → 再找主线 → 后精选股**
2. **数据可信度先于结论**
3. **风格切换看市场，不看心情**
4. **每日 30–90 分钟闭环**；收盘后 1–2 小时内完成复盘
5. 情绪阈值按月度校准；绩效按周期检验

---

## 执行总流程

```
步骤0 数据基建（互验+来源标注+北向现状）
    ↓
每日闭环：宏观 → 大盘 → 板块 → 个股 → 心态 → 策略
    ↓
选股漏斗：L1流动性 → L2策略初筛 → L3技术共振 → L4按风格校准
    ↓
工作流分流：短线 / 波段 / 长线（禁止混用校准路径）
    ↓
风控执行：仓位闸门 → 开仓五条件 → 仓位公式 → 熔断 → 止损止盈
    ↓
次日再复盘（绩效闭环）
```

完整结构图与五模块分工见 @references/00-overview.md。

---

## 硬门禁（Fail-Fast，优先于一切输出）

> 细则见 @references/09-hard-gates-trust.md。脚本在 `scripts/`，状态在 `state/`。

| 门禁 | 动作 |
|------|------|
| **G1** | 先跑 `scripts/mcp_health.py`；必须提供逐来源样例探活与时间戳，名称匹配/公网探测不算 MCP 可用证据 |
| **G2** | **mode=C 禁止买入清单**，只允许观察池 + 强制风险提示 |
| **G3** | mode=B 仅允许候选/观察，不允许开仓；需补足独立来源后再评估 |
| **G4** | 关键价冲突无第三源 → 该票不进买入清单 |
| **G5** | `scripts/circuit_breaker.py --state state/account_state.json` allow=false → 禁止新开仓 |
| **G6** | 每票 `position_calc.py` allow_open=false → 仅观察 |
| **G7** | 交付前报告 lint 必须明确 `PASS`；`FAIL/ERROR/NOT_RUN` 均阻断整体许可 |
| **G8** | 指数收盘、成交额、涨停数须有新鲜且独立双源证据；缺失/过期/冲突均阻断开仓 |

**推荐执行顺序（一键）**：

```bash
python scripts/run_pipeline.py \
  --available "tdx,ifind,eastmoney" \
  --probe-file probe-evidence.json \
  --market-data market-data.json \
  --tickers tickers.json \
  --report 路径/报告.html
```

`tickers.json` 中的候选按数组顺序分配剩余组合容量；示例结构见 `examples/tickers.example.json`。

流水线内部顺序：

```
mcp_health(逐来源证据) → circuit_breaker(只读评估) → G8市场数据互验
→ 逐票 tech_score+五条件+仓位 → report_lint(PASS 必需)
→ audit_write → state/pipeline/*_summary.json
```

`--probe` 仅为公开网络连通性诊断，不证明列出的 MCP 可用，也不能单独提升模式。
宿主需将逐来源结果写入 `--probe-file`；格式必须包括来源名称、独立来源 ID、成功状态、样例字段、有限数值样例和样例时间戳。
`--market-data` 必须提供 `index_close`、`turnover`、`limit_up_count` 三项，每项含汇总值和时间戳，并逐来源提供成功状态、原始值、时间戳及独立来源 ID。指数收盘差异须小于 0.1%、成交额差异小于 1%、涨停数完全一致。逐票还须提供数值型 `entry`、`entry_sources` 和 `sector`；多个候选按 JSON 数组顺序分配剩余组合仓位，并累计单票、板块与总仓暴露。缺少报告或市场数据时，流水线可生成观察/审计结果，但整体许可保持关闭。
完整 JSON 字段约定见 @references/09-hard-gates-trust.md。

---

## 步骤 0 · 数据基建（任何分析前必做，不可跳过）

**目标**：保证指数收盘、资金流向、涨跌停等关键数据点可信；若宿主 Agent 未连接金融行情 MCP，先提示用户连接。

### 0.1 先检查 MCP 连接（强制）

执行技能后**第一件事**：查看当前会话实际提供给 Agent 的 MCP/工具清单，并确认是否有能查询指数、个股行情或其他金融市场数据的来源。按实际能力判断，不能只凭服务器名称或公网可访问性认定已连接。

**若当前会话没有任何可用金融行情 MCP，必须先提示并询问用户，再继续行情分析**：

> 当前 Agent 会话没有发现可用的金融行情 MCP，因此暂时无法可靠获取和互验最新行情。请在当前 Agent 软件的 MCP/工具设置中连接金融行情数据源；建议至少连接 2 个相互独立的来源，且至少 1 个 P0（如同花顺 iFinD、通达信或东方财富妙想）。连接后请让我重新检查。若你希望现在继续，请明确选择“无 MCP 降级继续”；我会按模式 C 输出显著风险提示，不把弱源或用户提供数据冒充为 MCP 互验，也不会生成买入清单或开仓许可。

用户选择连接时，停止行情分析并等待其完成配置后再检查；用户明确选择降级继续时，才进入模式 C。若宿主没有向 Agent 暴露 MCP/工具清单，不能断言“未连接”；应说明当前无法核实，并请用户确认或提供可用工具信息。

当已检测到金融行情 MCP 后，再运行健康脚本：

```bash
python scripts/mcp_health.py --available "通达信,同花顺iFinD,东方财富" --probe-file probe-evidence.json
```

| 优先级 | 名称 | 识别关键词 |
|--------|------|------------|
| P0 | 同花顺 iFinD | iFinD / 同花顺 / 10jqka |
| P0 | 通达信 | 通达信 / tdx / TDX |
| P0 | 东方财富（妙想） | 东财 / 东方财富 / eastmoney / 妙想 |
| P1 | 万得 | 万得 / Wind |
| P1 | 腾讯自选股 | 腾讯自选股 / 自选股 / qqstock |
| P1 | Tushare | tushare / Tushare |

**门槛：已探活且相互独立的行情源 ≥ 2**（用于互验保真），且至少 1 个 P0。
「已连接」≠「可用」：每个来源须能样例拉数、返回非空值且时间戳合理（见 09 §9.4）。
`--probe` 只探测公开网络连通性，不计入 MCP 可用数；名称匹配也不构成探活证据。

| 可用数 N | 数据模式 | 动作 |
|----------|----------|------|
| N ≥ 2 | A · MCP 互验 | 主源+备源交叉验证后输出；**允许**买入清单 |
| N = 1 | B · 单源降级 | 单源+尽量网络补核；文首提示；仅列候选/观察，不形成开仓许可 |
| N = 0 | C · 网络弱源 | 网络/同类技能；**强制风险提示**；**禁止买入清单** |

复盘文首必须输出「【数据源状态】」；模式 B/C 必须含提示模板（见 @references/01-data-foundation.md §1.0）。

### 0.2 取数与校验硬规则

1. 按 @references/01-data-foundation.md 的**数据源优先级表**取数；**MCP 优先，网络为降级**。
2. 关键数字做**多源互验**（≥2 独立源一致 → 高可信）。
3. **每一条数据做准确性校验**（字段/时间戳/量级/方向/来源/互验状态）。
4. **没取到的数据强制留空 + 写提示**，禁止编造、估算、用其他日期冒充。
5. 冲突按表处理；不足时使用**降级话术模板**。
6. 全文强制**来源标注**：`（来源：东财妙想 MCP，YYYY-MM-DD 收盘；可信度：高）` 或 `（判断，非数据）`。
7. **北向资金**：2024 年起实时口径已收紧；终端无数据时写「实时数据不可得，跳过」，禁止按旧规则硬填。
8. 情绪阈值默认值会漂移；每月首个周末用近 60 日重算，写入 `state/sentiment_calibration.json`。
9. 复盘完成后写 `templates/audit-log.md` 到 `state/audit/YYYY-MM-DD.md`。

颜色约定（A股）：涨红 `#ef232a`，跌绿 `#14b143`。

---

## 每日闭环（六步 SOP）

顺序固定：**宏观 → 大盘 → 板块 → 个股 → 心态 → 策略**。

| 步骤 | 目的 | 关键输出 |
|------|------|----------|
| 1 宏观消息 | 定大势 | 偏多/中性/偏空 + 主线候选 2–3 条 + 风险事件 |
| 2 大盘指数 | 看整体 | 强/中/弱 + 风格标签 + 情绪阶段 + 总仓位区间 |
| 3 板块资金 | 找主线 | 主线 1–2 + 备选 1 + 龙头名单 + 板块阶段 |
| 4 个股技术 | 精选股 | 基本面结论 + 技术分 + S/A/B/C + 止损位/距离% |
| 5 心态纪律 | 修内功 | 情绪剥离 / 计划执行 / 扛单 / 成败各 1 条 |
| 6 策略执行 | 定操作 | 次日完整作战单（买什么、什么价买多少、什么价必须走） |

详细指标、量价口诀、情绪周期表见 @references/02-daily-loop.md。

**情绪周期**（阈值以本机校准表为准，未校准须标注使用默认值）：

```
冰点 → 修复 → 发酵 → 高潮 → 分歧 → 退潮 → 冰点
```

**复盘末尾必写五维总结**：整体市场 / 资金特点 / 板块特点 / 个股特点 / 技术特点 + 一句格言。

---

## 选股漏斗

```
全市场 → L1流动性 → L2策略初筛 → L3技术共振 → L4按风格校准 → 核心池5–15只
```

| 层 | 规则 |
|----|------|
| **L1** | 20日均成交额 ≥ 1亿；剔除ST/退市风险/长期停牌；默认可剔除科创688与北交8开头 |
| **L2** | 按风格选策略组合；默认 `all + score + top50`，人工砍到15以内 |
| **L3** | GMMA + 一目均衡 + ADX 共振评分；只留 S/A/B；C 丢弃 |
| **L4** | **必须先定工作流风格再校准**；短线禁套DCF，长线禁只看圆桌 |

L2 策略清单与组合模式、L3 评分表、L4 分流表见 @references/03-stock-funnel.md。

---

## 三条工作流

| 工作流 | 周期 | 核心路径 | 禁止 |
|--------|------|----------|------|
| **A 短线** | T+1~数日 | 每日六步复盘 → 技术快诊 → 主线+地位+止损距离 | 十分钟测试、DCF、护城河深度 |
| **B 波段** | 数周~数月 | 批量策略初筛 → 技术诊断 → 多周期研判 | 仅凭圆桌满仓 |
| **C 长线** | 1年+ | 十分钟测试 → 五维 → DCF+安全边际 | 仅凭圆桌/概率分开仓 |

每周一次全景（工作流D）：自上而下 + 板块RPS + 全策略排序 + 长线深析。

详细步骤见 @references/04-workflows.md。

**技术评分（满分100）前置硬门槛**：流动性≥1亿，否则 REJECT。

信号分级：S(90+) / A(75–89) / B(60–74) / C(<60)。参考仓位是**上限**，实际首仓用公式反推。

---

## 仓位与风控

### 总仓位闸门（大盘+情绪决定）

| 市场状态 | 总仓位 |
|----------|--------|
| 放量上攻 + 情绪发酵 | 70–100% |
| 结构性震荡 | 40–70% |
| 缩量阴跌 / 退潮 | 20–40% |
| 系统性风险 / 冰点未确认 | 0–20% |

### 开仓五条件（缺一不可）

1. 账户熔断未触发
2. 风格明确且 L4 已按该风格校准
3. 技术信号 ≥ B，且非反向信号并存
4. 首仓% 过公式且 ≤ 单票/单板块上限
5. 盘前清单已写：止损、加仓、止盈、最差情景与证伪条件

### 仓位公式（强制）

```
止损距离% = (买入价 - 止损价) / 买入价 × 100
首仓% = min(信号参考仓位%, 单票上限%, 单笔风险上限% / 止损距离%)
```

**必须用脚本计算，禁止手写拍脑袋**：

```bash
python scripts/position_calc.py --entry 10.0 --stop 9.4 --signal-cap 20 --stock-cap 15 --risk-cap 1 --style 波段 --grade S
```

该简化命令只演示仓位公式；由于未提供熔断、L4、反向信号、计划、G8、组合暴露和画像许可的显式核验，结果不会通过开仓门禁。止损距离过宽（>12%）导致仓位过低时：**放弃或等更好买点**，禁止为凑仓位放宽止损。

技术分同样用脚本：

```bash
python scripts/tech_score.py --adx 32 --turnover-20d-avg-yi 12 --gmma-bull --above-cloud --tenkan-gt-kijun
```

### 用户风险画像（适用性）

读取 `state/user_risk_profile.json`（无则用稳健默认并提示）。  
`per_trade_risk_pct`、`single_stock_cap_pct`、`allow_limit_up_board`、`output_mode` 必须代入计算与输出。详见 @references/10-user-profile-output.md。

### 账户熔断

| 条件 | 动作 |
|------|------|
| 回撤 ≥ 8% | 总仓减半，停新开仓 3 日 |
| 回撤 ≥ 12% | 停新开仓 ≥1 周 |
| 连续 3 笔止损 | 当日停开仓，复盘风格错配 |
| 单月亏 ≥10% | 当月剩余总仓 ≤30% |
| 单周亏 ≥6% | 下周总仓上限降一档 |

完整约束、一字跌停预案、绩效闭环见 @references/05-risk-control.md。

---

## 输出格式要求

### 优先级（强制）

1. **首选：HTML 单文件报告**（自包含、可直接浏览器打开/分享）
2. **次选：结构化 Markdown**（当环境无法生成/预览 HTML 时）
3. 无论 HTML 还是 Markdown，**内容完整度标准相同**，不得因格式降级而缩水

**输出粒度**（读用户画像 `output_mode`）：

| 模式 | 内容 |
|------|------|
| full（默认） | 完整六步 HTML/MD |
| summary | 数据源状态 + 五维 KPI + 主线 + 3 要点 |
| plan-only | 仅盘前作战单 + 门禁结果 |

summary/plan-only 仍必须保留：数据源状态、熔断、缺失标注、免责。

HTML 模板见 @templates/daily-report.html.md 与 @references/08-output-format.md。  
交付前：`python scripts/report_lint.py <报告文件>` 必须 PASS。  
合格/不合格样例：@examples/good-report-notes.md、@examples/bad-report-notes.md。

### 内容完整度硬标准（缺一不可）

复盘/规划报告必须同时覆盖下列模块；**缺项写「【缺失】+ 原因」**，禁止空段敷衍：

| # | 模块 | 最低完整度 |
|---|------|------------|
| 0 | 数据源状态 | 已连 MCP 列表、N、模式 A/B/C、风险提示（如有） |
| 1 | 元信息 | 日期、可信度、熔断、校准日、冲突/缺失清单 |
| 2 | 宏观消息 | ≥2 条关键消息 + 传导路径 + 主线候选 + 风险事件 |
| 3 | 大盘指数 | 主要指数涨跌/成交额 + 量价定性 + 情绪周期阶段 + 仓位闸门 |
| 4 | 板块资金 | 主力流向 TOP + 涨停结构 + 主线四问结论 + 阶段标注 |
| 5 | 个股诊断 | 持仓/候选逐只：逻辑、技术分、S/A/B/C、止损、距离%、首仓%、最差情景 |
| 6 | 心态纪律 | 情绪/计划/扛单/成败 + 3 行心得 |
| 7 | 明日策略 | 买入/卖出/观察三张清单 + 操作基调 + 风险禁区 |
| 8 | 五维总结 | 整体/资金/板块/个股/技术，各 1–3 句，有数字支撑 |
| 9 | 格言与免责 | 一句格言 + 不构成投资建议 |

**丰富度要求**（避免「骨架空转」）：
- 关键结论必须有 **数字 + 来源 + 可信度**，不能只写「偏强」
- 大盘、板块、个股至少各有一处 **对比**（环比、相对强弱、主线 vs 非主线）
- 策略区每只票必须可执行：**什么价买、买多少、破哪必须走**
- 缺失数据强制留空，但模块标题仍保留并标注缺失原因

### 通用规则

1. 凡引用具体数字/消息，句末必须标来源与可信度。
2. 数据不足强制降级话术；禁止编造关键行情。
3. 反向字段强制：每笔计划同写「最差情景 1 条 + 证伪条件」。
4. A 股颜色：涨 `#ef232a`，跌 `#14b143`（HTML/Markdown 一致）。
5. 生成 HTML 时：单文件、内联 CSS、无外链依赖、可离线打开。

---

## 项目内工具与状态

| 路径 | 用途 |
|------|------|
| `scripts/run_pipeline.py` | **一键流水线**：健康→熔断→票面→lint→审计 |
| `scripts/mcp_health.py` | MCP 匹配 + **真探活** + 模式 A/B/C |
| `scripts/position_calc.py` | 止损距离、首仓%、开仓五条件 |
| `scripts/tech_score.py` | GMMA+云层+ADX 技术分与 S/A/B/C |
| `scripts/circuit_breaker.py` | 账户熔断状态读写与门禁 |
| `scripts/report_lint.py` | 报告模块/来源/门禁违规检查 |
| `scripts/audit_write.py` | 自动写 `state/audit/YYYY-MM-DD.json/md` |
| `scripts/weekly_stats.py` | 台账周度胜率/盈亏比/纪律率 |
| `scripts/fill_weekly_report.py` | 按周期过滤台账 + 熔断 → 周复盘自动填空 |
| `scripts/calibration.py` | 情绪阈值月度分位校准 |
| `state/*.json` | 熔断、校准、用户画像、台账、pipeline/audit |
| `examples/good-report.html` | **Golden 样例**（report_lint 必须 PASS） |
| `templates/audit-log.md` | 人类可读审计模板 |
| `CHANGELOG.md` | 版本变更 |

MCP 字段映射见 @references/12-mcp-fetch-map.md。  
周复盘先跑 `fill_weekly_report.py`，禁止手写胜率。  
交付前跑 `report_lint.py examples/good-report.html` 可对照 Golden。

非 A 股需求先读 @references/11-multi-market.md，并降低结论强度。

---

## 免责声明

本体系为分析与学习框架，**不构成任何投资建议**。  
市场有风险，投资需谨慎。数据不足时如实标注，关键决策请自行验证并独立承担结果。
