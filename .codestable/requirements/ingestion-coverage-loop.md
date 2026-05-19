---
doc_type: requirement
slug: ingestion-coverage-loop
pitch: 让每份文档从页面到知识单元都有覆盖凭证。
status: current
last_reviewed: 2026-05-17
implemented_by:
  - closed-loop-architecture
tags:
  - ingestion
  - coverage
  - source-units
---

# 入库覆盖闭环

## 用户故事

- 作为知识库维护者，我希望知道文档哪些页面、块和知识单元已经入库，而不是只看到“解析完成”。
- 作为调试者，我希望能定位未覆盖 source unit，而解析高风险页面由解析质量闭环给出根因，而不是靠人工翻 PDF 猜漏了哪里。
- 作为系统验收者，我希望入库结果有可量化指标，而不是只看生成文件数量。

## 为什么需要

如果入库阶段没有覆盖凭证，后面的召回失败无法判断是“没召回到”还是“内容根本没进来”。KB1 必须先证明文档真的被解析成可追踪的 pages、blocks、evidence、facts 和 source_units。

## 怎么解决

系统把文档拆成页面、块、证据、事实和 source unit，并生成覆盖报告。维护者可以看到解析成功率、证据数量和未覆盖单元，从源头判断知识链是否完整。页面级解析风险由解析质量闭环承接，避免入库覆盖和解析质量互相污染。

新文档接入必须有独立验收口径：pipeline 跑完后运行 `validate-document-ingestion`，检查 document、pages、blocks、evidence、facts、wiki、source_units、coverage artifact、coverage 阈值、answerability 和 document knowledge contract。该验收报告决定文档是否真正进入入库闭环，而不是只看命令是否执行完成。

Document knowledge contract 是文档类型无关的验收合同。系统按知识类型检查已经出现的 source unit 是否能追踪到 evidence/fact，事实是否匹配统一 evidence shape，并且是否有 active golden case 进入回归保护。合同失败表示入库链路断裂；合同 warning 表示链路可用但质量闭环不完整。

合同必须覆盖普通 generated golden 和 corpus eval golden。普通 golden 以 `golden_cases.doc_id` 指向文档；corpus eval 以 `metadata.expected_doc_id` 指向文档。两种来源都应计入 active golden 覆盖，避免跨 suite 评估无法支撑入库验收。

Requirement 知识类型必须独立建模为 `requirement` evidence shape，不能混入 parameter 或 process。用户问“有哪些要求/规定”时，系统应允许 requirement/table_requirement 作为合法证据形状，并进入 golden/corpus 回归。

自动 golden 闭环必须保留证据形状约束。coverage draft、promotion、去重、DB 同步都要携带 `expected_evidence_shape`，否则 active golden 无法证明某类知识被回归保护。

Source unit 生成必须先过滤目录点线、页码目录、图例、表格语法和纯符号残片。目录条目不能成为 requirement 覆盖义务；这类噪声应在入库闭环源头归因和过滤，而不是在召回、答案或某个失败 case 上打补丁。

## 边界

- 不保证每个 source unit 都能直接回答用户问题。
- 不负责判定低可读性页面是否需要 OCR 修复；这属于解析质量闭环。
- 不替代召回质量评测；它只证明内容是否进入知识库。
- 需要先完成文档注册和解析流程。
