# V0.6 IMPL-001 Implementation Notes — Graph Context Builder

- Date: 2026-09-04 · Baseline: 3610c99（V0.6 design）· V0.5 frozen e7a286e（零触碰实测）
- 新增：agent_kb/kgraph/context.py（GraphContextBuilder + GraphReasoningContext +
  ProvenanceRecord + GraphContextError）

## 行为契约（VC-CMP-001..010 全 PASS）

- **context 创建**（001）：immutable frozen dataclass；全字段
  （context_id/fingerprint/root_entity/graph_fingerprint/input_nodes/
  input_assertions/input_edges/temporal_context/status_filter/query_constraints/
  rule_set_version/provenance/hop）；
- **deterministic id**（002）：context_id = "grc_"+SHA256(canonical payload)[:16]；
  fingerprint = SHA256("v06-ctx-1.0|"+canonical)；同库状态三实例全等；
- **ordering 稳定**（003）：全列表 canonical 排序（nodes/assertions/edges/temporal/
  provenance by assertion_id）；
- **provenance 完整**（004）：每 assertion 记录 evidence_ids + document_ids——
  context→assertion→evidence→document 全链；缺源 fail-closed（E-V06-SOURCE-MISSING）；
- **status 规则**（006）：status_filter ∈ {valid,flagged}（默认）；invalidated 排除
  （source_id 不入 input_assertions）；root invalidated → E-V06-ROOT-INVALIDATED；
- **hypothesized 阻断**（007）：hypothesized 是 assertion_type（非 status）——
  V0.5 已排除出图，builder 输入面天然无此断言；
- **temporal 保留**（008）：temporal_context = "temporal:"+canonical(scope) 只读引用
  （V0.3 零重算）；temporal_required=True 且缺失 → E-V06-TEMPORAL-AMBIGUITY；
- **Query boundary**（009）：kg 数据全经 GraphQueryService（源码审计零 "FROM kg_nodes"；
  kg_projection_runs fingerprint 元数据面除外）；root 不存在/参数越界 fail-closed
  （E-V06-ROOT-NOT-FOUND/INVALID-HOPS 1..4/INVALID-STATUS-FILTER/CONTEXT-TOO-LARGE）；
  build 只读（五表快照前后一致）；
- **V0.5 regression**（010）：build 前后 canonical_view 不变；input_assertions 可直接
  作为 V0.4 engine.reason(parent_ids) 输入（下游接口实测兼容）。

## 断言关联语义（设计落地细节）

断言进入 context 的判定（全部在已取数据上判定，零额外 SQL）：
①relates_to/supports 边的 provenance_ref 指向该断言；②断言 payload 的
subject_ref/object_value 命中邻域 entity canonical_form 集；③断言节点在邻域/边端点。

## P1 发现（不改 frozen，待 owner 决策）

IMPL-003 persist 对"fingerprint 变化但含相同 node_id"的重投影（新增断言后全量重建）
会触发 kg_nodes PK 冲突——V0.5 冻结语义与全量重建路径的兼容缺口。V0.6 不改 frozen；
影响：追加断言后的全量 repersist 需等 V0.6 后续任务（设计 supersede 语义已备）或
owner 授权的 V0.5 change-control。VC-CMP-006 以模拟已持久化状态验证 builder 行为。