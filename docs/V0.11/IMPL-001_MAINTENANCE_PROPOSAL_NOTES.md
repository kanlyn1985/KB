# V0.11 IMPL-001 Implementation Notes — Maintenance Proposal Runtime

- Date: 2026-09-04 · Baseline: 2e89a4f（V0.11 design）· V0.5..V0.10 frozen（零触碰
  实测——唯一 frozen 面变更 = verification.py VALID_TASK_TYPES 枚举扩展，设计
  明示授权，生命周期/identity/审计零修改）
- 新增：agent_kb/maintenance/（runtime.py + __init__.py——新包）；tests/
  v11_maintenance/test_maintenance_proposal.py（V11-MAINT-CMP-001..012）

## 行为契约（V11-MAINT-CMP-001..012 全 PASS）

- **create from signal**（001）：health signal → MaintenanceProposal 全字段
  （proposal_id=V0.8 task_id / source_type / source_id=信号行粒度 /
  proposal_type="maintenance_review" / spec 固定模板 / priority 映射 /
  status=created）；
- **create from conflict**（002）：hypothesis 型 target 正路提案；entity 型
  target fail-close（E-V11-MAINTENANCE-INVALID——P1 定标默认档，零 fabricate）；
  conflict status 零变更（Conflict ≠ Resolution 实测）；
- **deterministic proposal_id**（003）：V0.8 verification_task_identity 复用
  （零新算法）——同信号跨实例全等；不同信号不同 id；
- **fingerprint stability**（004）：canonical payload hash 16 hex 稳定；
- **immutable**（005）：frozen dataclass 赋值拒绝 + 重复 create 幂等零重复审计；
- **proposal→task**（006）：task 实存（V0.8 get_task）+ task_type 白名单 +
  status=created 零自动迁移（human-only）+ 原有 task_type（evidence_review）
  行为不变（枚举扩展零破坏）；
- **no assertion mutation**（007）：提案全流程 akb_assertions unchanged 快照；
- **no graph mutation**（008）：kg_nodes/kg_edges unchanged + hypothesis 状态
  零变化；
- **provenance audit**（009）：graph:maintenance-proposal-create 落
  akb_provenance（proposal_id/source/target/spec/priority——零第二套审计）；
- **invalid source fail-close**（010）：不存在 signal/conflict、未知 source_type、
  limit 超帽、坏 cursor、坏 id 全拒（E-V11-MAINTENANCE-INVALID）；
- **cursor query deterministic**（011）：三信号两页无重无漏 + 重放一致 +
  source_type 过滤 + conflict 锚 fail-close 验证；
- **frozen regression**（012）：frozen 模块零感知（verification.py 仅枚举扩展
  断言）+ legacy 互斥 + 建图回归（canonical_view 不变）。

## 关键实现决策（实现期定标——设计 P1 项落地）

1. **锚解析 fail-close**（P1 定标默认档）：V0.8 create_task 硬校验 hypothesis
   实存——entity/assertion 型 target 无实存 hypothesis 时 fail-close
   （E-V11-MAINTENANCE-INVALID），零 fabricate 锚；hypothesis 型直接校验使用。
   这比设计的"created_from 派生锚"更严格（派生锚会被 V0.8 硬校验拒绝——
   诚实边界优于绕行）；
2. **spec 确定性模板锁定**（P1 定标）："Please review ... (health finding/
   conflict flagged, human review required)"——零自由文本漂移，零裁决性结论；
3. **source_id 粒度 = 信号行 id**（health_id:signal_type）——诚实反映提案来源
   行；proposal_id 仍由 V0.8 算法派生（spec/evidence_requirements 含行 id）；
4. **输入前提**：提案消费 V0.10 持久面——health/conflict 需先经 persist
   落表（设计 ARCHITECTURE §2 数据流）；未持久化信号 → fail-close NOT-FOUND。

## Migration Decision

**NO MIGRATION 维持**——proposal 走 V0.8 task 通道（生命周期与审计既有）。
migration 18 触发条件延续设计记录（①提案独立长期查询需求 ②proposal/source
大规模反向索引需求）。

## P0/P1/P2

- P0 = 0（零 frozen 语义修改；六条红线全部 fail-close 实测）
- P1 = 0（两项设计 P1 定标项已落地：锚解析 fail-close + spec 模板锁定）
- P2 = 1（批量提案生成——同快照多信号一键提案集，accepted 候选延续）