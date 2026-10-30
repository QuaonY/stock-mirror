# StockMirror HTML 复盘报告骨架（生成时按此拼装）

> 说明：本文件是**结构契约**，不是最终交付。实际交付请生成独立 `.html` 单文件。  
> 样式可微调，章节与字段不得删减；缺数据用 `【缺失】+ 原因`。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>StockMirror · 股海镜鉴 · 复盘 YYYY-MM-DD</title>
<style>
  :root {
    --up: #ef232a;      /* 涨 */
    --down: #14b143;    /* 跌 */
    --ink: #1a1a1a;
    --muted: #666;
    --line: #e5e5e5;
    --bg: #f7f7f8;
    --card: #fff;
    --warn-bg: #fff7e6;
    --warn-border: #ffd591;
    --ok: #2f9e44;
    --bad: #e03131;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px;
    font: 14px/1.6 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: var(--ink); background: var(--bg);
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  header.brand {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 12px 0 20px; border-bottom: 2px solid var(--ink);
  }
  header.brand h1 { margin: 0; font-size: 22px; font-weight: 700; }
  header.brand .sub { color: var(--muted); font-size: 12px; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 12px; border: 1px solid var(--line); background: #fff;
  }
  .badge.mode-A { color: var(--ok); border-color: var(--ok); }
  .badge.mode-B { color: #d48806; border-color: #d48806; }
  .badge.mode-C { color: var(--bad); border-color: var(--bad); }
  .warn {
    background: var(--warn-bg); border: 1px solid var(--warn-border);
    border-radius: 8px; padding: 12px 14px; margin: 16px 0;
  }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }
  .kpi {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 12px 14px;
  }
  .kpi .k { color: var(--muted); font-size: 12px; }
  .kpi .v { font-size: 18px; font-weight: 700; margin-top: 4px; }
  .up { color: var(--up); }
  .down { color: var(--down); }
  .miss { color: var(--muted); background: #f1f3f5; padding: 0 4px; border-radius: 4px; }
  section {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px 18px; margin: 14px 0;
  }
  section h2 {
    margin: 0 0 12px; font-size: 16px;
    padding-bottom: 8px; border-bottom: 1px solid var(--line);
  }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #fafafa; font-weight: 600; }
  ul { margin: 8px 0 0 18px; padding: 0; }
  .muted { color: var(--muted); }
  footer {
    margin-top: 28px; padding-top: 16px; border-top: 1px solid var(--line);
    color: var(--muted); font-size: 12px;
  }
  @media (max-width: 720px) {
    .kpis { grid-template-columns: 1fr 1fr; }
  }
</style>
</head>
<body>
<div class="wrap">

  <header class="brand">
    <div>
      <h1>StockMirror · 股海镜鉴</h1>
      <div class="sub">以市场为镜，鉴往知来 · 复盘报告</div>
    </div>
    <div class="sub">
      YYYY-MM-DD
      · <span class="badge mode-A">模式 A · MCP互验</span>
    </div>
  </header>

  <!-- 1 数据源状态 -->
  <div class="warn">
    <strong>【数据源状态】</strong>
    已连接 MCP：____、____（N=__）；
    模式：A/B/C；
    冲突/缺失：____。
    <!-- 模式 B/C 必须追加完整风险提示与「建议连接 MCP」文案 -->
  </div>

  <!-- 2 元信息 -->
  <section>
    <h2>元信息</h2>
    <div class="kpis">
      <div class="kpi"><div class="k">数据可信度</div><div class="v">高 / 中 / 低</div></div>
      <div class="kpi"><div class="k">账户熔断</div><div class="v">正常 / 保护期</div></div>
      <div class="kpi"><div class="k">情绪阈值校准日</div><div class="v">____</div></div>
    </div>
  </section>

  <!-- 3 五维速览 KPI -->
  <section>
    <h2>五维速览</h2>
    <div class="kpis">
      <div class="kpi"><div class="k">大盘</div><div class="v">强 / 中 / 弱</div></div>
      <div class="kpi"><div class="k">量能</div><div class="v">放量 / 缩量 / 平量</div></div>
      <div class="kpi"><div class="k">情绪阶段</div><div class="v">冰点…退潮</div></div>
      <div class="kpi"><div class="k">主线</div><div class="v">____</div></div>
      <div class="kpi"><div class="k">建议总仓位</div><div class="v">__%</div></div>
      <div class="kpi"><div class="k">开仓基调</div><div class="v">进攻/均衡/防御</div></div>
    </div>
  </section>

  <!-- 4 宏观 -->
  <section>
    <h2>步骤1 · 宏观与消息</h2>
    <ul>
      <li>大势定性：偏多 / 中性 / 偏空（判断依据 + 来源）</li>
      <li>关键消息1：____（来源：____；可信度：高/中/低）</li>
      <li>关键消息2：____（来源：____）</li>
      <li>传导路径：____</li>
      <li>主线候选：____</li>
      <li>风险事件：____</li>
    </ul>
  </section>

  <!-- 5 大盘 -->
  <section>
    <h2>步骤2 · 大盘与指数</h2>
    <table>
      <tr><th>指数</th><th>涨跌</th><th>成交额</th><th>来源/备注</th></tr>
      <tr><td>上证</td><td class="up">+0.00%</td><td>____亿</td><td>____</td></tr>
      <tr><td>深证</td><td class="miss">【缺失】</td><td class="miss">【缺失】</td><td>原因</td></tr>
      <!-- 创业板 / 科创50 等 -->
    </table>
    <ul>
      <li>量价定性：____（相对 5/20 日）</li>
      <li>情绪：涨停 __ / 跌停 __ / 连板 __ / 炸板率 __%（来源）</li>
      <li>情绪阶段：____（对照校准表）</li>
      <li>仓位闸门：__%–__%</li>
    </ul>
  </section>

  <!-- 6 板块 -->
  <section>
    <h2>步骤3 · 板块与资金</h2>
    <table>
      <tr><th>主线</th><th>逻辑</th><th>持续性</th><th>龙头</th><th>阶段</th><th>证据（资金/涨停）</th></tr>
      <tr><td>____</td><td>____</td><td>____</td><td>____</td><td>启动/加速/分歧/退潮</td><td>____</td></tr>
    </table>
    <p class="muted">主力净流入 TOP：____ · 北向：可得/不可得（规则变更则跳过）</p>
  </section>

  <!-- 7 个股 -->
  <section>
    <h2>步骤4 · 个股与技术</h2>
    <table>
      <tr>
        <th>代码名称</th><th>风格</th><th>逻辑</th><th>技术分</th><th>信号</th>
        <th>止损</th><th>距离%</th><th>首仓%</th><th>最差情景/证伪</th>
      </tr>
      <tr>
        <td>____</td><td>短/波/长</td><td>____</td><td>__</td><td>S/A/B/C</td>
        <td>____</td><td>__</td><td>__</td><td>____</td>
      </tr>
    </table>
  </section>

  <!-- 8 心态 -->
  <section>
    <h2>步骤5 · 心态与纪律</h2>
    <ul>
      <li>情绪剥离：____</li>
      <li>计划执行：____</li>
      <li>扛单：____</li>
      <li>成功/失败各 1 条：____</li>
      <li>今日 3 行心得：做了什么 / 为什么 / 下次怎么改</li>
    </ul>
  </section>

  <!-- 9 策略 -->
  <section>
    <h2>步骤6 · 明日策略</h2>
    <p><strong>操作基调：</strong>____</p>
    <table>
      <tr>
        <th>代码</th><th>动作</th><th>买入区间</th><th>止损</th>
        <th>加仓</th><th>止盈1</th><th>止盈2</th><th>一字跌停预案</th>
      </tr>
      <tr><td>____</td><td>买/卖/观察</td><td>____</td><td>____</td><td>____</td><td>____</td><td>____</td><td>有/无</td></tr>
    </table>
    <p class="muted">绝对禁区：____</p>
  </section>

  <!-- 10 五维总结 -->
  <section>
    <h2>五维市场总结</h2>
    <ol>
      <li>整体市场：____</li>
      <li>资金特点：____</li>
      <li>板块特点：____</li>
      <li>个股特点：____</li>
      <li>技术特点：____</li>
    </ol>
  </section>

  <footer>
    <p><strong>格言：</strong>涨时重势，跌时重质 / 别人恐惧我贪婪 / 耐得住寂寞，守得住繁华 / 抓住主线，远离噪音（按当日特点选一）</p>
    <p>StockMirror · 股海镜鉴 — 本报告为分析与学习框架，不构成任何投资建议。市场有风险，投资需谨慎。</p>
  </footer>

</div>
</body>
</html>
```

## 生成检查（对 AI）

- [ ] 是否输出了独立 `.html` 文件（或在可用预览通道交付）？
- [ ] 模式 B/C 是否有显著风险提示？
- [ ] 持仓/候选是否逐只字段完整？
- [ ] 是否有编造数字？有则改回 `【缺失】`
- [ ] 是否可离线打开？
