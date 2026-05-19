---
doc_type: audit-index
slug: core-regression-integrity
status: current
created_at: 2026-05-18
scope:
  - query-chain
  - evidence-shapes
  - answer-policy
  - ingestion-pipeline
  - regression-tests
  - workspace-doctor
summary: 核心回归完整性审计，重点检查以前可用能力退化的系统性原因
---

# Core Regression Integrity Audit

## Scope

本次审计聚焦会导致“以前好的功能越改越坏”的核心路径：

- 查询改写、召回、Graph、证据形状、答案策略
- 文档重建 pipeline、coverage/source unit 同步
- MCP/API/测试对真实 `knowledge_base` 的写入边界
- 回归用例、UI delivery asset、workspace doctor 与架构文档的一致性

## Evidence Collected

- `C:\Python314\python.exe -m pytest -q`
  - 结果：295 passed, 6 failed, 903 deselected
- `C:\Python314\python.exe -m compileall -q src tests`
  - 结果：passed
- `workspace-doctor --scope all --json`
  - 结果：warn，主要是 wiki missing source fact、retrieval/eval stale runs
- `workspace-doctor --scope coverage --json`
  - 结果：ok，但未发现 `DOC-000003` 已经没有 source units
- 当前 DB 快照：
  - `DOC-000003` pages=157
  - `DOC-000003` evidence=317
  - `DOC-000003` facts=185
  - `DOC-000003` source_units=0
- `CP控制导引是什么意思` 当前回归：
  - rewrite 仍保留 `CP控制导引`
  - evidence judge 判定 insufficient
  - top hits 已漂移到 ASPICE / V2G
  - 直接答案退化为标准/发布日期或 V2G 文本

## Overall Assessment

当前最大问题不是某一个 query prompt，也不是 PDF 解析单点，而是 **状态治理和测试隔离没有跟上系统复杂度**。尤其是测试和 MCP 工具会直接对共享 `knowledge_base` 执行 destructive rebuild；一旦重建质量下降或中途阶段产出为空，真实库会被污染，后续查询就表现为“之前好，现在突然坏”。

这解释了用户观察到的核心现象：功能不是稳定退化，而是被共享 DB 状态、过期 golden 合同、缺少原子重建和缺少 doc-level doctor 检查共同放大。

## Findings Matrix

| ID | Severity | Type | Confidence | Finding | Suggested Action |
|---|---|---|---|---|---|
| F-01 | P0 | bug / arch-drift | high | MCP build_document 测试直接重建真实 DOC-000003，污染共享知识库 | cs-issue |
| F-02 | P0 | bug / arch-drift | high | 文档 pipeline 是多阶段 destructive commit，缺少原子性/回滚/验收门 | cs-issue |
| F-03 | P1 | bug | high | workspace-doctor coverage 对“某文档 source_units=0”漏报 | cs-issue |
| F-04 | P1 | maintainability / arch-drift | high | user-style regression golden 合同与当前 query_type 设计不一致 | cs-issue |
| F-05 | P2 | maintainability | medium | demo delivery asset 测试仍断言旧 tab 集合，UI 合同已漂移 | cs-issue |

## Priority Recommendation

1. 先修 F-01 + F-02：禁止测试和工具无保护地破坏真实 `knowledge_base`，并让 document rebuild 具备 staging/rollback/acceptance gate。
2. 再修 F-03：doctor 必须能发现当前这种“coverage scope ok 但关键文档 source_units=0”的状态。
3. 然后修 F-04：把 golden/regression 合同升级成“行为合同”，不要继续用过期 `expected_query_type=definition` 约束参数含义类问题。
4. 最后修 F-05：同步 UI delivery asset 测试，让它验证真实页面结构，而不是过时字符串。

## Immediate Risk

当前 `knowledge_base` 已被全量测试过程污染，`DOC-000003` 没有 source units，CP 控制导引相关查询会继续失败。进入修复前应先确认是否要恢复/重建 `DOC-000003`，但不能直接用现有破坏性 pipeline 盲目重建；需要先处理 F-01/F-02 的安全边界。

## Resolution Notes

2026-05-18 已完成第一轮根因修复：

- F-01：MCP `build_document` 测试改为临时 workspace + 临时文档，不再重建共享 `knowledge_base` 的真实 `DOC-000003`。
- F-02：document pipeline 增加 DB backup/restore 和 ingestion acceptance gate；验收失败时回滚，不激活半成品派生状态。
- F-03：`workspace-doctor --scope coverage` 增加 doc-level source unit 缺失检查，能发现“pages/evidence/facts 存在但 source_units=0”的污染状态。
- 解析根因：PDF fast-text profile 不再只看文本覆盖率，还检查 readability、symbol/unreadable ratio；乱码文本层会回退到 MiniMax/Astron/PaddleVL 慢路径。
- 解析选择根因：parse view 评分把结构分数与可读性、重复行、页眉页脚噪声绑定，避免 PyMuPDF HTML 的伪章节号把乱码/逐字换行页抬成 selected view。
- 数字 PDF 结构化根因：PyMuPDF 文本块按通用章节号和步骤号拆成 heading/paragraph blocks，避免整页文本作为一个段落导致 procedure facts 缺失。
- 答案衔接根因：answer 层选择 primary doc 时尊重 evidence judge 的 best_fact_ids 顺序，不再用多数投票覆盖第一个最佳事实。
- 召回根因：test method 查询增加 direct process-fact 注入；OBC 对象锚点改为内容级强约束，文件名只提供弱提示，且 `OBC输入` 这类中英文相邻写法能被正确识别。

复验结果：

- `DOC-000003` 重建：`parser_engine=minimax_primary+astron_backup`，`fact_count=1293`，`source_unit_count=707`，ingestion acceptance `warn`、0 failed。
- `DOC-000009` 重建：`process_fact=81`，`source_unit_count=170`，test coverage `0.9647`，ingestion acceptance `warn`、0 failed。
- `CP控制导引是什么意思`：返回 `控制导引功能 control pilot function; CP: 用于监控电动汽车和供电设备之间交互的功能。`
- `OBC输入过压怎么测`：返回 `5.4.1 交流输入过、欠压保护试验` 的 a/c/d 步骤，不再落到逆变附录。
- `workspace-doctor --scope coverage`：不再有 failed issue；当前仍有 1 个 warn，来自 `DOC-000009_definition_10_3` 的 `weak_definition_shape`，属于后续 source-unit 分类质量项。

2026-05-18 后续修复：

- `DOC-000009_definition_10_3` 的 `weak_definition_shape` 根因是 `knowledge_units._looks_like_definition_term` 只要求正文包含“是/用于/通过”等解释词，未排除表格数值块；“功能特性状态要求”后接状态/百分比/工频周期矩阵，被误配成 definition unit。
- 修复：定义候选正文增加通用 table-value body 判定，数字密度、状态/等级/Hz/%/工频周期等表格 token 过高时不允许生成 definition unit。
- 重建 `DOC-000009` 后 `workspace-doctor --scope coverage` 为 `ok`，无 warn/fail。
