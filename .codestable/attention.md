# Attention

本文件是 CodeStable 技能启动必读的项目注意事项入口。所有 CodeStable 子技能开始工作前必须读取它。

## 项目碎片知识

<!-- cs-note managed: 用 cs-note 维护，新条目按下面分节追加 -->

### 编译与构建

### 运行与本地起服务
- 项目工作目录固定为 `E:\AI_Project\opencode_workspace\KB1`。
- 知识库运行根目录是 `knowledge_base`，CLI 需要显式传 `--root knowledge_base`。
- 本地 API 启动命令：
  `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base serve-api --host 127.0.0.1 --port 8000`
- API 健康检查：
  `http://127.0.0.1:8000/health`

### 测试
- 快速回归优先跑：
  `C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q`
- 带 `-k` 过滤时，pytest 输出大量 `deselected` 是正常现象，表示未匹配过滤表达式的测试被跳过。
- **默认套件状态（Sprint 3 完成后，2026-06-30）**：`716+ passed, 1 skipped, 0 failed, 0 xfailed`（~5min，默认 deselect integration+benchmark）。全量套件（`-o addopts=""` 取消 deselect）含大量 integration/benchmark，会很慢且有失败，正常回归不要跑全量。
- **定义查询 xfail 已解除（Sprint 2 WP2）**：原 `test_mcp_server_tools_call_answer_query` 的 xfail 已移除并通过。根因是 `_inject_direct_term_definition_hits` 只处理短缩写，中文长术语定义查询（如 `什么是控制导引电路？`）没注入权威 term_definition，导致选错文档回填标题。修复见 issue `2026-06-24-definition-query-exact-term-gate-drops-evidence`。
- **post_ingestion_gate 测试**用 `tmp_path` 隔离 fixture，不触生产库；不要改回硬编码 `DOC-000001`（那是孤儿 doc_id）。

### 命令与脚本陷阱
- `query-context` 和 `answer-query` 的查询文本必须使用 `--query` 参数，不能作为位置参数传入。
- PowerShell here-string 直接写中文有时会变成 `????`；HTTP 或 Python 脚本验证中文查询时优先使用 Unicode escape 字符串。
- 短缩写定义问题如 `CP是什么意思`、`CC是什么意思` 应先走歧义澄清或规则扩写，不应先交给 LLM 扩写。

### 路径与目录约定
- 源码目录：`src\enterprise_agent_kb`。
- SQLite 和生成知识库资产位于 `knowledge_base`。
- CodeStable 文档入口位于 `.codestable`，旧文档暂不移动，迁移需用户逐项确认。
- 每一步开发都必须同步更新文档：代码改动完成后，至少核对并更新 `.codestable` 中对应的 architecture / requirement / roadmap / feature / issue 文档；若行为、接口、命令、开发流程或用户操作发生变化，还必须同步更新 `docs/dev` 或 `docs/user` 指南。

### 环境变量与凭证
- Advanced Query Planner 默认关闭；需要实验链路时设置 `EAKB_ENABLE_ADVANCED_QUERY_PLANNER=1`。

### 其他
- **Sprint 1 稳定化（2026-06-24）已完成**：8 个失败测试收口为 0 failed+1 xfail；WIP 分 13 个本地 commit（safety tag `safety/pre-sprint1-stabilization-20260624`，**未 push**，远端不可达）；eval baseline 固定为 token_overlap（deterministic，0.60）；工程清理已 quarantine 0字节db + prune 陈旧 run。详见 `docs/dev/sprint1-stabilization/sprint1_acceptance_report.md`。
- **Sprint 2（2026-06-25）进展**：(1) WP0 67+ commit 已 push 到 origin/kb1-six-loop-rename（成果保护完成）；(2) WP2 定义查询 bug 修复（CJK term_definition 召回），MCP xfail 解除，默认套件 696 passed/0 failed/0 xfail；(3) WP3/WP4 ontology 最小接入（off/shadow/guard 只读 adapter，默认 off 零开销，`answer_changed_by_ontology` 全程 False）；(4) WP5 eval 采样修复——`_round_robin_sample` 跨文档采样 + 问题提质过滤，**诚实锁定真实跨文档基线 pass_rate=0.30**（0.60 旧值是单文档偶然，作废）。详见 `docs/dev/sprint2-ontology-and-bugfix/`。
- **文本 LLM 契约**：所有文本 LLM 调用统一走单一 `text_llm` provider（`get_text_llm_settings()` 读 `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/`TEXT_LLM_MODEL`），无 minimax→astron 两段 fallback。详见 `docs/dev/llm-provider-policy.md`。OCR/parse provider 路由（minimax+astron+paddle）与此无关，仍多 provider。
- **Sprint 3（2026-06-30 已完成）**：4 Gate 中 3 完全达成（0 baseline 复现 / 2 ontology A/B 安全 / 3 104 题分片可跑），1 部分达成（1 eval 0.30->0.40 真实提分，距 0.65 deferred Sprint 4）。WP0-WP10 全部完成并 push origin。首提真实提分（_anchors CJK fallback，0 artifact）；反 metric-gaming（anti-degradation guard）；orphan facts 治理（72 隔离 + 12 召回过滤）；104 题 golden 分片（shard-run/merge-shards）；性能修复 20q 20+min->7.5min。详见 `docs/dev/sprint3-answer-quality/sprint3_acceptance_report.md`。前序：WP2 P0 硬降级（`_should_downgrade_for_insufficient_evidence` sufficient=False AND conf<0.2 时降级）+ doc-selection fix（`_choose_doc_from_evidence_judgement` best_fact_ids=[] 时回退 best_evidence_ids 投票）+ P3 噪声题收紧 + metric 防降级完成。诚实真实基线 20 题 pass_rate=0.40（[4][12] CJK 回退提分，Sprint 3 首个实质提分）（[6] 元数据降权后）。WP3 query_rewrite 锚点拆分（整句 must_term→should_terms 锚点）让 [4][12] 正确文档进入候选（召回改善），pass_rate 无变化无回归。
- **eval 主口径**：`eakb eval run-now --suite golden --version v1 --max-questions 20`（token_overlap，无 LLM，跨文档轮询采样）。Sprint 3 完成后当前诚实基线 **20 题真实 pass_rate=0.40（0 artifact，453s）**；CI smoke floor `--min-token-pass 0.20`。`EVAL_USE_LLM=1` 才启用 LLM judge（辅助非阻塞）。10 题样本太小（恒 0.30），已扩到 20 题以稳定反映质量。详见 `docs/dev/eval-baseline-policy.md`。
- **Sprint 3 P3 噪声题收紧 + metric 防降级**：`_is_noise_expected_point` 在 `_generate_questions_for_point` 顶部跳过噪声 point（封面/页眉/SC码/英文片段），题池 100→87（0 噪声残留）；`_is_degraded_answer` 让降级答案（证据不足/未找到）强制 cov=0，消除降级文本与英文 point 共享 token 的假通过。不换 metric 只加固。
- **命名**：主线 six-loop；历史 `kb1-four-loop-hardening` roadmap 目录与 `four-loop-integration` audit 保留原名（维持引用链），已加历史命名说明；新工作走 `kb1-next-phase`。
- **eval 性能（Sprint 3 WP9）**：20q eval 默认走完整召回管道（含 embedding+semantic），单跑 20+min。跑 eval 时设 `EAKB_DISABLE_EMBEDDING_SEARCH=1 EAKB_DISABLE_SEMANTIC_SEARCH=1 EAKB_ENABLE_LLM_EVIDENCE_JUDGE=0` 可降到 7.5min（0.40 结果不变）。104 题用 `eakb eval shard-run --shard-index I --shard-count N` 分片 + `merge-shards` 合并。
- **Requirement Resolver 叠加子系统（2026-07-13 已合并）**：客户/项目维度 OBC/DCDC 需求治理层，28 张 requirement_* 表（IF NOT EXISTS，不与既有 30 表冲突），21 模块 6559 LOC 在 `src/enterprise_agent_kb/requirements/`。三个集成点：①CLI `eakb requirement <subaction>`（38 子动作，`cli/_requirement.py` 适配器）；②answer_api 软路由（**默认关闭**，`EAKB_ENABLE_REQUIREMENT_ROUTER=1` 启用，仅 requirement_effective/diff/conflict_scan 三意图且 confidence>=0.75 介入，否则返回 None 既有链不变）；③api_server FastAPI 适配（可选）。解析器确定性，不让 LLM 决定有效需求值，evidence_judge 仍是唯一事实裁决边界。KB1 fast suite 810 passed/0 failed（基线 734+76），check_health 10/10，生产 DB 未变。技术债：schema 待迁移到 `migrations/0xx_requirement_program.sql`。评审报告 `docs/kb1_requirement_program_review.html`。
- **NEXT_DEVELOPMENT_PLAN Phase 1 进行中（验证链修复）**：6 阶段工程收敛路线图（docs/NEXT_DEVELOPMENT_PLAN.md，用户在 GitHub 主分支直接编写）。Phase 1 三任务：①修复 run_requirement_program.py / audit_requirement_program.py 的测试发现路径（tests/requirement/）与 audit 期望（cli/ 包结构、docs/requirement-program/ 子目录）；②重写 3 个 apply_requirement_*.py 集成脚本适配模块化 cli/ 架构，提供函数式库 API（integrate_cli/integrate_answer_api/integrate_api_server）+ CLI 幂等包装，72 requirement 测试全过；③在 .github/workflows/tests.yml 新增 requirement-program CI job（windows-latest + Python 3.12，7 步：checkout/setup/install/clean pycache/pytest tests/requirement/audit/smoke）。17/17 smoke gate + 11/11 audit 通过。
- **项目阶段评审报告（持续更新）**：`docs/kb1_project_review_2026-06-24.html` 是<b>活的评审报告</b>，<b>每个 Sprint 完成后必须更新</b>（用户拿它做阶段评审）。新增 §09 "Sprint 进展"章节按 Sprint 追加；同步更新执行摘要(§01)/测试(§05)/当前状态(§10)/风险(§11)/结论(§13) 的统计与评级。更新后用 Python HTMLParser 校验标签平衡。Sprint 1 已更新（2026-06-25，总体 A-）。
