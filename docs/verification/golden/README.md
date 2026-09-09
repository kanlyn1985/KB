# Golden Knowledge Dataset V1.0

> 任务：AKB-P0-GOLDEN-001 · 基线：SRS V1.1 / Data Model V1.0 / ICD V1.0 / V&V Plan V1.0 / RTM V1.0
> 状态：Draft（待架构评审）

## 定位

知识面 Golden 基准：**Evidence → Assertion → Reasoning → Answer Contract** 四层期望。
服务 V&V Plan §24（Golden 回归）、§15（推理验证）、§14（充分性/答案验证）与 RTM SYS-018。

## 与既有 golden_cases.json 的关系（防重复建设说明）

| | 本数据集 | `docs/ontology/tree_skeleton/llm_landing/golden_cases.json` |
|---|---|---|
| 层次 | 知识面（DM-003/005/012 对象级期望） | 检索面（query→节点候选） |
| 规模 | 30 case | 234 case |
| 消费者 | Knowledge Verification / Reasoning Regression / Answer Contract / Agent E2E | `run_retrieval_health.py`（词法通道） |
| Schema | `schema/golden_case.schema.json` | 无 schema（runner 内联判定） |

两套数据层次不同、互为补充；manifest `companion_assets` 已交叉引用。**不合并**——
检索面 case 只有 `query/expected` 两字段，承载不了 Evidence/Assertion/Reasoning 期望。

## 结构

```text
golden/
├── README.md                  ← 本文件
├── schema/golden_case.schema.json
├── cases/G001..G030.json      ← 30 case，每类 1 个
└── manifests/golden_v1.0.json ← 冻结清单（case_ids + category_index + coverage）
```

## 验证（离线，零 LLM）

```bash
python agent_kb_core/tools/validate_golden_dataset.py
# Golden Dataset validation: PASS / Cases: 30 / Invalid: 0 / Duplicate IDs: 0
```

pytest 集成：`agent_kb_core/tests/test_golden_dataset.py`（同样离线）。

## 关键设计约定

1. **Evidence 双轨**：`evd:node:<node>:<n>` 引用生产库 29528 条既有证据（不复制不搬移）；
   `evd:gold:<id>` 是 golden 本地精选证据（含 excerpt/document/location）。
2. **Assertion 严格分型**：`asserted/validated` 必有 `evidence_refs`（INV-001）；
   `inferred` 必有 `derivation` 块（rule/parent/reasoner，INV-002）；状态走 DM-005 §9.4 生命周期。
3. **Reasoning 6 例覆盖四型**：graph multi-hop(G007)、temporal(G008)、conflict-aware(G016)、
   rule(G019/G020)、cross-layer multi-step(G021)。
4. **Negative 11 处期望**：G030 集中三条任务书 NEG（无证据不成断言/derived 不冒充 asserted/
   证据不足不出确定答案），其余分散在各 case 的 `negative_expectations`。
5. **领域锚定**：全部 case 基于 OBC/DCDC 真实骨架节点与生产库证据，不用虚构领域。

## 冻结规则

Expected 结果一经评审冻结，修改必须升版本（V1.1+）并过架构评审（V&V §24：
Golden Set 不允许静默修改 expected result）。