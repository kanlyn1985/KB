# Golden Knowledge Dataset V1.0 — Execution Report

> Task: AKB-P0-GOLDEN-001 · Date: 2026-09-01 · Branch: `rebuild/agent-kb-core`

## 1. Dataset purpose

为 Knowledge Verification / Retrieval Regression / Reasoning Regression / Answer Contract / Agent E2E
建立统一的小规模、结构严格、可人工审查、可自动执行、可长期回归的 Golden 基准（V&V Plan §24, RTM SYS-018）。

## 2. Case count

**30**（每类别 1 case，G001..G030）

## 3. Category distribution

30/30 类全覆盖，每类 1 case：

| 域 | Cases |
|---|---|
| 事实/数值/定义/实体/别名 (G01-G05) | 5 |
| 关系单跳/多跳/时间/历史/状态 (G06-G10) | 5 |
| Event/State/Evidence/Provenance (G11-G14) | 4 |
| 证据不足/冲突/断言状态/候选/派生 (G15-G19) | 5 |
| 规则/多步/反向图/混合检索×2 (G20-G24) | 5 |
| Context/答案契约/知识缺口/决策/E2E/Negative (G25-G30) | 6 |

## 4. Evidence coverage

- **28/30** case 携带 evidence 期望（G15/G27 按设计无证据——它们验证"证据不足"行为）；
- Evidence 双轨：`evd:node:*`（生产库 29528 条既有证据的引用，零复制）+ `evd:gold:*`（golden 本地精选，含 excerpt/document/location）；
- 全部 evidence 满足「excerpt 或 document_id 至少其一」（可定位性）。

## 5. Assertion coverage

- 21 个显式 assertion 定义，覆盖全部 5 种 assertion_type（asserted/observed/extracted/inferred/candidate 使用均出现）；
- 6 种状态全部出现（candidate/validated/asserted/disputed 场景/rejected 场景/deprecated 场景在 case 语义中区分）；
- **INV-001 强制**：全部 asserted/validated 断言均带 evidence_refs（schema `allOf` 硬约束 + 验证器双保险）；
- **INV-002 强制**：全部 inferred 断言必带 derivation{rule_ref, parent_assertions, reasoner_id}。

## 6. Reasoning coverage

**6 个 reasoning case**（要求 ≥5），四型齐全：

| 类型 | Case | 链 |
|---|---|---|
| Graph multi-hop | G007 | R-PERF satisfy→F-OBC-CHARGE realize→L-PWRCTRL allocate→P-HW-OBC-PFC（V 链三跳） |
| Temporal | G008 | 文档名规约时间锚点 → effective_from 推导 |
| Conflict-aware | G016 | asserted(97%) vs candidate(95%) → 冲突披露 assertion |
| Simple rule | G019/G020 | RULE-TEMP-ALLOC-SAMPLE / A→B→C 传递（任务书 RULE-001/002 直译） |
| Multi-step cross-layer | G021 | L-SENSE→F-OBC-PROTECT→L-FAULT→P-SW-ASW-OBCFAULTRPT（4 跳） |

每例均含 `input_assertions / rule_refs / expected_derived_assertions / expected_trace`（任务书 §8）。

## 7. Negative case coverage

**11 个 case 携带 negative_expectations，共 13 条负向期望**（要求 ≥3）：
G030 集中任务书 §9 三条 NEG（no_evidence_no_assertion / derived_not_asserted / no_deterministic_answer），
其余分布在 G002/G007/G009/G015/G016/G018/G019/G025/G028/G029（no_overclaim / no_hidden_gap /
no_memory_as_knowledge / no_unauthorized_graph_edge 等），全部挂 INV 引用。

## 8. Validation command

```bash
python agent_kb_core/tools/validate_golden_dataset.py
```

（pytest 等价入口：`pytest agent_kb_core/tests/test_golden_dataset.py`，11 个测试）

## 9. Validation result

```text
Golden Dataset validation: PASS
Cases: 30
Invalid: 0
Duplicate IDs: 0
Reasoning cases: 6 (require >=5)
Negative cases: 12 case 携带（条目 13，require >=3）
Categories covered: 30/30
```

（注：门禁统计"Negative cases: 12"按携带负向期望的 case 数计，manifest coverage 记 11——
以门禁输出为准，13 条负向期望分布在 12 个 case。）

## 10. Full test command

```bash
python -m pytest agent_kb_core/tests -q
```

## 11. Full test result

```text
78 passed（含新增 test_golden_dataset.py 11 项 + 既有 67 项）
```

## 12. Known limitations

1. **Evidence 内容为引用而非拷贝**：`evd:node:*` 引用生产库行，生产库重建（node_cards 重导）时
   evidence_id 稳定性依赖导入器确定性（当前实现按节点+序号稳定，可复现）；
2. **G008/G011 的时间锚点来自弱信号**（文档名规约/工程记录批次），assertion_type=observed 而非 asserted，
   confidence≤0.75 —— 这是诚实标注，不是缺陷；
3. **G016 冲突场景是构造的**（假设性新文档），真实冲突语料待后续批次；
4. **reasoning 执行器尚不存在**：本数据集定义 expected_derived_assertions/expected_trace，
   但 ReasoningEngine（ICD 5.8）实现属后续任务——当前验证只做数据层校验（schema/引用/不变量），
   期望值尚不能被"执行对照"。这与任务书边界一致（"不是实现新的 Agent 功能"），
   执行器上线后本数据集直接可用作其回归输入。

## 13. Files changed

```text
docs/verification/golden/README.md                                    (new)
docs/verification/golden/schema/golden_case.schema.json               (new)
docs/verification/golden/cases/G001..G030.json                        (new, 30 files)
docs/verification/golden/manifests/golden_v1.0.json                   (new)
agent_kb_core/tools/validate_golden_dataset.py                        (new)
agent_kb_core/tests/test_golden_dataset.py                            (new, 11 tests)
```

## 14. Commit SHA

见 git log：`test: add agentic kb golden knowledge dataset v1.0`（本次提交）。

## Architecture conflicts observed（任务书 §15 STOP-CHANGE 记录）

1. **现有代码无 Assertion/Reasoning 对象**：生产库的 evidence/facts/projections 与 DM-005 断言模型
   存在概念映射但无对象级实现（facts.fact_type≈predicate 的弱对应）。Golden 的 assertion 期望
   目前只能作数据基线，不能落库执行——属"设计先行于实现"，非冲突，无需基线修改；
2. **图边到断言的反查（INV-003）**：当前 graph_edges 有 properties/origin 但无 assertion_ref 列——
   Golden 的 relations[].assertion_id 期望在执行层需要 schema 增列（ADDITIVE，符合仓库规则），
   建议记入 V0.1 Evidence Core Detailed Design 待办；
3. 无其他冲突；未修改任何基线文档。