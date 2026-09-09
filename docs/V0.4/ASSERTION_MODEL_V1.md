# V0.4 Assertion Model V1 — Inferred Assertion Canonical Model

- Document ID: AKB-DD-V04-002 · Status: Design Baseline
- 原则：**prefer extension over duplication**——不新建 assertion 表/不并行模型；
  inferred 断言复用 V0.1 `akb_assertions` 全部既有结构（assertion_type=inferred +
  derivation_json 已在 schema 内）。

## 1. 模型复用审计（为什么零 schema 变更）

| 需求 | 既有载体 | 结论 |
|---|---|---|
| assertion_type=inferred | akb_assertions.assertion_type（CREATE_ALLOWED_TYPES 含 inferred） | 复用 |
| derivation 链 | akb_assertions.derivation_json（rule_ref/parent_assertions/reasoner_id 已被 V0.2 create_candidate 校验） | 复用 + V0.4 扩展键 |
| provenance | akb_provenance（activity 枚举可扩 infer） | 复用 |
| 治理状态机 | akb_assertions.status + LEGAL_TRANSITIONS（inferred→asserted 已禁止） | 复用 |
| 推理 run 审计 | **新表 akb_reasoning_runs（migration 14 设计——本文档只设计）** | 新增（论证见 §3） |

## 2. Inferred Assertion 字段语义（V1 定案）

```text
KnowledgeAssertion(assertion_type="inferred"):
    subject_ref / predicate_ref / object     # 同既有语义
    status = "candidate"                     # 恒定（R-01）
    evidence_refs = ∪ parent.evidence_refs   # R-05（溯源到最终 Evidence）
    source_unit_refs = ∪ parent.source_unit_refs
    confidence = round(weighted(parent confidences, rule weight), 4)
    derivation_json = {
        rule_ref: "<rule_id>@<rule_version>",
        parent_assertions: [assertion_id, ...],       # 非空（INV-002）
        reasoner_id: "<provider_id>",
        rule_input_snapshot: CanonicalJSON,           # V0.4 新增键：审计回放
        confidence_basis: {...},                      # V0.4 新增键：置信来源
        synthesis_run_id: ...,                        # 若 parent 含 V0.3 产物（穿透溯源）
    }
    ontology_scope / temporal_scope / provenance_ref   # 同既有
```

## 3. 新表 akb_reasoning_runs（migration 14 设计——只设计不执行）

```sql
CREATE TABLE IF NOT EXISTS akb_reasoning_runs (
    run_id             TEXT PRIMARY KEY,
    parent_ids_json    TEXT NOT NULL,        -- canonical 排序 parent assertion_id
    reasoner_id        TEXT NOT NULL,
    rule_version       TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    actor_id           TEXT NOT NULL,
    policy_version     TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN
                        ('running','completed','failed','partial')),
    proposals_json     TEXT,                 -- InferredProposal 快照
    fingerprint        TEXT,                 -- ReasoningFingerprint（锚，UNIQUE）
    warnings_json      TEXT NOT NULL DEFAULT '[]',
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_akb_reasonruns_fingerprint
    ON akb_reasoning_runs(fingerprint);
CREATE INDEX IF NOT EXISTS ix_akb_reasonruns_status ON akb_reasoning_runs(status);
```
论证：V0.2 CompilationRun/V0.3 SynthesisRun 同款 run 级聚合先例——provenance 表粒度
是单次动作，无法回答"哪次推理用了哪些 parent/哪个规则版本"；锚语义延续
（首个 completed run 持 fingerprint，UNIQUE；产物经 run 反查）。
V0.1/V0.2/V0.3 既有表零改动（纯新增，DROP 可逆）。

## 4. 状态机交互（继承不变）

- creation：create_candidate(assertion_type="inferred", derivation=...)（唯一边界）；
- inferred → validated：允许（actor=human/system），治理复核须引用独立证据；
- inferred → asserted：**永久禁止**（State Machine 现行约束保持——V0.4 不改）；
- rejected/deprecated：同既有路径。

## 5. 与 hypothesis 的关系

hypothesized 类型仍按 V0.1 约束（只能保持 candidate）；V0.4 不改变其语义——
inferred 与 hypothesized 的区别：inferred 有完整 derivation chain（机器可回放），
hypothesized 是人工/agent 提出的未证实命题（无 rule 依据）。