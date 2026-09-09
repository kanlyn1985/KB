# V0.12 IMPL-002 Implementation Notes — Analytics Query Layer

- Date: 2026-09-04 · Baseline: 34d1ce9（IMPL-001）· V0.5..V0.11 frozen（零触碰
  实测——仅 analytics/query.py 新增 + __init__ 导出 + 新测试）
- 新增：agent_kb/analytics/query.py（AnalyticsQueryRuntime + AnalyticsQueryCursor
  + AnalyticsReportPage + AnalyticsQueryError）；tests/v12_analytics/
  test_analytics_query.py（V12-ANALYTICS-QUERY-CMP-001..012）

## 行为契约（V12-ANALYTICS-QUERY-CMP-001..012 全 PASS）

- **basic query**（001）：5 报告全查（items/report_id ASC/next_cursor=None）；
- **scope filtering**（002）：global 精确匹配 / 未知 scope 零结果；
- **metric filtering**（003）：白名单通过（knowledge_growth）/ 未知 metric
  fail-close（E-V12-QUERY-INVALID）；
- **cursor pagination**（004）：5 报告 limit=2 三页遍历无重无漏（零 OFFSET）；
- **cursor replay**（005）：同 cursor same output；
- **invalid cursor**（006）：篡改指纹/错 query kind（V0.10 causal cursor
  binding 拒绝）/非法 JSON 三分支 fail-close（E-V12-QUERY-CURSOR-INVALID）；
- **deterministic ordering**（007）：report_id ASC 多次查询一致（零 created
  time/memory order/DB natural）；
- **empty result**（008）：items=[]/cursor=None/has_more=False 零 fabricate；
- **readonly isolation**（009）：akb_assertions/kg_nodes/kg_edges unchanged
  快照实测；
- **no governance bridge**（010）：查询零产生 proposal/task/maintenance action
  （计数实测——Analytics ≠ Governance Action 红线锚定）；
- **provenance replay**（011）：同 provenance 跨实例恢复同 report identity/
  fingerprint；
- **frozen regression**（012）：V0.5..V0.11 十六 frozen 模块零感知 + legacy
  互斥 + 建图回归（canonical_view 不变）。

## 关键实现决策

- 报告源唯一 = akb_provenance（graph:analytics-report-create）——零新表；
- metric filter 白名单 = V0.12 IMPL-001 METRIC_WHITELIST 复用（零第二套）；
- cursor kind = "analytics_report_query"（query binding——V0.10 causal/
  V0.11 maintenance cursor 复用拒绝实测）；
- AnalyticsReportPage 契约字段 = items/next_cursor/has_more（任务书定义——
  无 count 字段）。

## Migration Decision

**Migration 19 NOT REQUIRED 维持**——报告源 = provenance metadata；零新表
（akb_analytics_reports 未创建）/零 ALTER/零索引变更。

## P0/P1/P2

- P0 = 0（mutation 零 / automatic bridge 零 / identity violation 零）
- P1 = 2（cursor payload size——canonical JSON 报告 id 粒度当前 <200B/cursor ·
  provenance scan performance——全表 LIKE 扫描在大基数下需索引优化（V0.10 P1
  延续项））
- P2 = 3（analytics report diff / materialized analytics view / report
  export——均需新任务书）
- large report set ordering = report_id ASC keyset 稳定性已实测（007）。