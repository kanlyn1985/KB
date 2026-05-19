---
doc_type: audit-finding
slug: document-pipeline-destructive-non-atomic
severity: P0
type:
  - bug
  - arch-drift
confidence: high
suggested_action: cs-issue
---

# F-02 Document Pipeline Is Destructive And Non-Atomic

## Finding

`run_document_pipeline` 按 parse、quality、evidence、facts、entities、wiki、graph、coverage、acceptance 顺序直接写主库。多个阶段会先删除当前 doc 的旧数据再写入新数据；阶段之间没有统一事务、staging 表、回滚策略或“验收通过后再切换”的提交点。

## Evidence

- `src/enterprise_agent_kb/pipeline.py:106-184` `_run_document_pipeline` 顺序执行各阶段。
- `src/enterprise_agent_kb/parse.py:828-829` 删除当前 doc 的 `blocks` 和 `pages`。
- `src/enterprise_agent_kb/parse.py:950-955` parse 阶段独立 `commit`。
- `src/enterprise_agent_kb/facts.py:1314-1317` facts 阶段删除旧 `fact_evidence_map` 和 `facts`。
- `src/enterprise_agent_kb/closed_loop_store.py:29-31` coverage sync 删除当前 doc 的 `source_unit_fact_map`、`source_unit_evidence_map`、`source_units`。

## Impact

任意阶段产出质量下降、异常或空结果，都可能把原本可用的文档打成半重建状态。当前 `DOC-000003 source_units=0` 就是这种模式的表现之一。它会直接破坏召回、Graph、coverage、golden 和答案链路。

## Root Cause

入库闭环把“构建”和“替换当前有效知识”混在一起了。缺少 staging generation、acceptance gate、rollback 和版本化 active snapshot。

## Suggested Fix

- 引入 document rebuild staging：新 pages/evidence/facts/source_units/wiki/graph 先写 staging 或新版本 namespace。
- 只有 `validate-document-ingestion` passed/warn 且关键合同满足时，才切换 active version。
- 失败时保留旧 active version，并把新版本标记为 failed build artifact。
- 对 operator-facing build 命令增加 `--force-activate` 或显式确认。

