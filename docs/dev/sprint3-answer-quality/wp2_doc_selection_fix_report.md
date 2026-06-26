# Sprint 3 WP2 — answer_context_routing 文档选择修复（[6][15] 缺陷）

> Sprint 3 WP2（P0 + 文档选择修复）。依据：`docs/dev/sprint3-answer-quality/kb1_failure_taxonomy_report.md` §8 逐案根因。
> 本 WP 含两处修复：P0 硬降级（`e3e4da7`，已 push）+ `[6][15]` best_evidence_ids 回退（本提交）。

## 1. 缺陷：sufficient=True 但 best_fact_ids 为空时丢文档

**位置**：`src/enterprise_agent_kb/answer_context_routing.py` `_choose_doc_from_evidence_judgement`

**根因**（调用链证据）：
- case [6]：`build_query_context` 返回 6 hits（DOC-000013，正确 V2G 文档），`evidence_judgement.sufficient=True conf=0.75`，但 `best_fact_ids=[]`（只有 `best_evidence_ids=['EV-049931']`）。
- `_choose_doc_from_evidence_judgement` 要求 `best_fact_ids` 非空才返回文档，故返回 None。
- 选文档 fallback 到错文档 → `_restrict_context_to_doc` 清空所有 hits → answer 输出「未找到」。
- case [15] 同理：5 条 best_evidence_ids 全映射 DOC-000013，但 best_fact_ids 空 → 同样清空。

**矛盾现象**：judgement 明明 sufficient=True 且有真实证据，答案却「未找到」。

## 2. 修复

在 `_choose_doc_from_evidence_judgement` 中：当 `sufficient=True` 且 `best_fact_ids` 为空时，回退用 `best_evidence_ids` → 通过 context 的 evidence/hits 映射到 doc_id，按出现次数取最多的 doc。

```python
if not best_fact_ids:
    best_evidence_ids = [...]
    if not best_evidence_ids:
        return None
    # map best_evidence_ids -> doc_id via context evidence + hits
    evidence_docs = {...}
    doc_votes = {doc: count}
    if doc_votes:
        return most_voted_doc
    return None
```

**低风险依据**：只在 `sufficient=True AND best_fact_ids=[]`（当前必失败路径）触发，happy path（best_fact_ids 非空）完全不走这段。纯证据驱动，无 LLM、不重写主链路、不换 metric。

## 3. 验证

### 3.1 文档选择修复

| 案例 | best_evidence_ids | 修复前 | 修复后 |
|---|---|---|---|
| [6] | [EV-049931] | 未找到（清空） | DOC-000013（正确）✅ |
| [15] | [5 条 evidence] | 未找到（清空） | DOC-000013（5/5 全对）✅ |

### 3.2 20 题样本 pass_rate

| | 修复前 | 修复后 | 变化 |
|---|---|---|---|
| pass_rate | 7/20 = 0.350 | 9/20 = 0.450 | +0.10 |

逐案：
- **[15]** cov 0.031 → **0.344 通过** ✅（真实提升，答案含 DOC-000013 V2G/智能电网真实内容）
- **[11]** cov 0.00 → **0.808 通过** ⚠️（**metric artifact，非真实提升**——见下）
- [4][13] cov 0.22/0.24 → 0.00（P0 降级转诚实「未找到」，仍 fail，符合预期）

### 3.3 ⚠️ 诚实披露：[11] 是 token_overlap artifact

[11]（`请解释: The Systems Engineer`）修复后答案变成 P0 降级文本「当前候选证据不足以给出确定性答案。期望证据形状：term_definition、parameter_definition、process_activity...」。该降级文本与 expected_point（英文 "The Systems Engineering process group... SYS.4 系统集成..."）共享 process/definition/system 等 token，token_overlap 算出 0.808 误判通过。

**这是 metric 被降级文本骗过，不是真实答案质量提升**。按 Sprint 3「不刷分」约束，[11] 不应计入真实提分。真实提分仅 [15]（+1 真实通过，0.350→0.400）。

**后续处理**：[11] 暴露 token_overlap 对降级文本的脆弱性——降级答案含「process/definition」等通用英文词会误通过。这是 metric 层问题，留 Sprint 3 后续或单独评估（不在本 WP 修，避免改 metric）。

### 3.4 回归

- fast suite：696 passed, 1 skipped, 0 failed（0 回归）
- check_health：10/10 PASS
- definition query（Sprint 2 fix）：仍正确（控制导引电路）

## 4. 边界合规

- ✅ evidence_judge 仍是唯一事实裁决边界（本修复只用 judgement 的 best_evidence_ids 选文档，不裁决事实）
- ✅ 不重写 query_api/answer_api 主链路（只改 answer_context_routing 一个函数的回退分支）
- ✅ 无 LLM、无新 vector DB
- ✅ 不换 metric、不删题、不降标准
- ✅ answer_changed_by_ontology 不涉及（本 WP 不动 ontology）

## 5. 真实净提分

- **真实提分**：+1（[15]，0.350→0.400）
- **metric artifact**：+1（[11]，不计入，已披露）
- **诚实提分**：0.350 → 0.400（+0.05 真实，+0.05 artifact 待 metric 层处理）

Sprint 3 Gate 1（0.65-0.85）仍远未达，需 P1（[5][17] 通道加权）+ P3（pseudo_question）+ [6] 答案质量（DOC-000013 证据取到但答案取了学术标题片段而非 V2G 段落）继续推进。
