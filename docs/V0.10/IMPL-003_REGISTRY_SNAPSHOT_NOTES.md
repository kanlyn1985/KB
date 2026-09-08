# V0.10 IMPL-003 Implementation Notes — Registry Snapshot Runtime

- Date: 2026-09-04 · Baseline: 9a6d73e（IMPL-002）· V0.5..V0.9 frozen（零触碰实测）·
  **MIGRATION DECISION: NO MIGRATION 维持**
- 新增：storage/registry_snapshot.py（RegistrySnapshotRuntime + RegistrySnapshot +
  registry_snapshot_identity + RegistrySnapshotError）；storage/__init__.py 导出；
  tests/v10_persist/test_registry_snapshot.py（V10-REGISTRY-CMP-001..012）

## 行为契约（V10-REGISTRY-CMP-001..012 全 PASS）

- **snapshot create**（001）：domain registry → RegistrySnapshot 全字段
  （snapshot_id/schema_version=1/registry_type/created_from/entries/
  fingerprint/provenance_refs）；
- **deterministic snapshot_id**（002）："rgs_"+SHA256(canonical_json
  ({registry_type, schema_version, entries}))——跨实例全等 + 单元复算；
- **fingerprint change detection**（003）：注册新 pack → id/fingerprint 双变；
- **canonical ordering**（004）：entries 按 entry_key ASC（跨插入顺序）；
- **immutable**（005）：frozen dataclass 赋值拒绝 + 重复 create 零重复审计；
- **restore**（006）：校验通过 + deterministic 载荷（双 restore 全等）；
- **invalid fingerprint fail-close**（007）：payload 篡改 → fingerprint mismatch
  拒绝；
- **invalid schema fail-close**（008）：schema_version≠1 / 未知 registry_type /
  坏 id 全拒；
- **provenance audit**（009）：graph:registry-snapshot-create 落 akb_provenance
  （snapshot_id/registry_type/entry_count/fingerprint）；
- **duplicate entry fail-close**（010）：同 key 双条目拒绝——**明确选择
  fail-close 而非静默去重**（同 key 双版本是语义冲突，显式暴露）；
- **no frozen mutation**（011）：akb_assertions/kg_nodes/kg_edges unchanged +
  registry 内容零变化（只读引用）；
- **full regression**（012）：四类 registry 全兼容（domain_pack/rule_package/
  policy/causal——entry 提取按对象形态自适应：pack_ref/package_ref/
  policy_ref/projection fingerprint）+ 四类 snapshot_id 互异 + query/persist
  层零干扰 + 建图回归。

## MIGRATION DECISION

**NO MIGRATION 维持**——snapshot payload 保存在 akb_provenance metadata
（graph:registry-snapshot-create）。理由：registry 快照为低频治理动作（跨进程
恢复时点触发），payload 为 registry 条目摘要（key@version + content ref——
非全量 pack 内容），基数 10^1-10^2 级，provenance metadata 完全可行。
**migration 18 触发条件**：①registry 条目数增长使全量 payload 超出 metadata
实用上限（单活动数十 KB 级）②需要快照间结构化 diff 查询。出现时按任务书评估。

## 关键实现决策

- entry 提取零新 identity 算法：content_ref 直接引用 runtime 已派生的
  pack_ref/package_ref/policy_ref/projection fingerprint（opaque 对象降级为
  repr hash——当前四类 registry 全部有原生 ref，未触发降级）；
- duplicate entry_key 选择 fail-close（任务书允许去重或 fail-close 二选一——
  选 fail-close：同 key 双版本是语义冲突，静默去重会掩盖注册错误）；
- policy registry value 兼容 dict 激活态与 str policy_ref 两形态。

## P0/P1/P2

- P0 = 0
- P1 = 1（snapshot replay consistency：跨进程恢复 = provenance 重放（seq 锚）
  + fingerprint 校验双保险——已实测；遗留：重放时 registry 原生对象重建
  （LoadedPack 等需要 pack source 重新 load）属消费方职责，本阶段交付确定性
  载荷）
- P2 = 2（payload size 风险：条目摘要级 payload 当前 <1KB/快照，10^3 条目
  才触及 metadata 实用上限——migration 18 触发条件监控 · registry version
  conflict：同 key 双版本由 fail-close 拒绝（010），load_order 消歧延续
  V0.7 语义）