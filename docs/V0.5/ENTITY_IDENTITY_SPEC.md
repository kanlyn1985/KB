# V0.5 Entity Identity Spec — Entity Identity Resolution

- Document ID: AKB-DD-V05-002 · Status: Design Baseline
- 继承：V0.3 对齐层级（L1/L2/L4 多键 + L3 type 级降权教训——V0.3-IMPL-002/004）、
  V0.5_KNOWLEDGE_GRAPH_SPEC KG-01（Evidence 唯一可信来源）。

## 1. Entity Canonical ID

- canonical_id = 确定性派生：`SHA256(CanonicalJSON({canonical_form, entity_type,
  domain_pack_version}))[:24]`，节点 id `ent_{canonical_id}`；
- canonical_form 选取：簇内成员按 (evidence_id, candidate_id) 最小序的 normalized_form
  （继承 V0.3 对齐簇 representative 规则——同簇跨 evidence 收敛）；
- 稳定性：同簇输入不变 → canonical_id 不变；簇变化 → 新 id（不重写历史 id——
  旧 id 经 merge 记录可追溯，见 §3）；
- entity_type 来源：DomainPack entity types（V0.3 对齐的 IDENTITY_CONFLICT 教训——
  type 分歧不得静默合并）。

## 2. Alias

- alias 列表 = 簇内全部成员的 surface_form/normalized_form 集合（canonical 序）；
- alias → canonical 解析表：DomainPack terminology（V0.3 L4 通道）+ 治理确认的
  显式别名（人工批准——不做自动 alias 学习）；
- alias 冲突（一个 alias 映射两个 canonical）→ 非法状态：E-V05-ALIAS-CONFLICT，
  治理复核入口（不自动消歧）。

## 3. Merge Policy（核心红线：禁止文本相似自动 merge）

**红线（任务书明确）：Entity A + Entity B 不能因为文本相似自动 merge。**

| 层级 | 条件 | 动作 |
|---|---|---|
| L1 精确 | normalized_form 完全一致 AND entity_type 一致 | 自动同簇（继承 V0.3 L1） |
| L2 归一 | V0.2 N 系归一后一致（含尾部系动词剥离等已固化规则）AND entity_type 一致 | 自动同簇（继承 V0.3 L2b） |
| L4 别名 | DomainPack terminology 或治理批准的 alias 映射 | 自动同簇 |
| L3 ontology_ref | **type 级引用，不作实例合并依据**（V0.3 教训固化） | 仅审计快照 |
| 相似度（编辑距离/embedding 余弦等） | **仅产生 merge candidate 建议** | 不自动合并——进治理队列 |
| 无共同 Evidence 支撑 | 两个候选簇 evidence 集合不相交 | 不合并（跨证据佐证为零）|

merge 判定必须同时满足：
M-01 L1/L2/L4 之一精确命中（相似度仅建议）；
M-02 entity_type 一致（type 分歧 → IDENTITY 分歧处理，见 §4）；
M-03 两簇 Evidence 集合存在共同支撑或治理批准（防跨文档同名误并）；
M-04 merge 动作本身携带 provenance（activity=merge，记录触发规则与批准者）。

## 4. Conflict Handling

- **IDENTITY 分歧**（同簇内 entity_type 不一致）：延续 V0.3 CONF-005 语义——
  不静默合并，转治理；Graph 层表现为分裂的双 EntityNode + contradicts 语义标注；
- **merge 回滚**：merge 记录（merged_from ids）保留；治理撤销 → 按 merge 记录
  逆操作恢复双簇（provenance 链支持——GRAPH_PROVENANCE_SPEC rollback）；
- **split**：误合并发现 → 治理发起 split（按成员 evidence 归属重划簇），
  旧 canonical_id deprecated 标记 + 新 canonical_id 生成（历史不断链）；
- 全部冲突处理是**治理动作**（human），Graph 层零自动裁决。

## 5. Provenance Requirement

- 每个 EntityNode 必须可回溯：canonical_id → 成员 assertion/candidate 列表 →
  SemanticUnit → Evidence → Document（零孤儿——KG-01）；
- merge/split/alias-approve 动作全部落 akb_provenance（activity=merge/split/alias），
  metadata 含 before/after 簇快照（CanonicalJSON）；
- Entity Resolution 引擎输出 resolution report（逐簇判定 + 规则引用 + 置信），
  治理可复核（继承 V0.3 rule_audit 模式）。

## 6. 与 V0.3/V0.4 的关系

- 复用 V0.3 EvidenceAlignmentEngine 的多键 union-find 产出作为候选簇（零重算——
  对齐引擎 frozen，V0.5 只做其输出之上的 identity 层）；
- inferred 断言的 subject/object 引用 canonical entity：经 derivation 链回溯的
  parent 断言实体（继承 V0.4 边界）；
- 不修改 V0.3 对齐代码——Entity Identity Resolution 是新模块（V0.5-IMPL-002）。