# definition-query-exact-term-gate-drops-evidence — Fix Note

> Issue fix (Sprint 2 WP2)。修复闭环记录。
> 修复时间：2026-06-25。

## 1. 修复入口

快速通道（从 report 直接触发），但 report 的根因判断不准确，WP2 先写了一份
`-analysis.md` **修订根因**，用户确认"对，就这样改"后进入 fix。

## 2. 修订根因（实际定位）

report 假设 `exact_terms=["控制导引电路"]` 触发 answer 层 gate 清零——**不成立**。
`_extract_exact_terms`（`answer_query_parsing.py:71`）正则 `[A-Z][A-Z0-9/-]{1,}` 只匹配纯拉丁大写，
纯中文查询 → `exact_terms=[]`，answer 层 gate 全部跳过，**没有清零上下文**。

真正清零的地方：`_choose_primary_doc_id`（`answer_context_routing.py`）**选错了文档**（DOC-000016，
来自 graph_candidates 兄弟扩展投票），随后 `_restrict_context_to_doc` 把全在 DOC-000012 的 4 条
evidence 过滤光 → 空上下文 → 降级回填文档标题。正确文档是 **DOC-000003**（权威 term_definition
FACT-013692 所在），但召回层 `_inject_direct_term_definition_hits` 只处理短缩写（`_short_definition_acronyms`
纯拉丁），中文长术语返回空 → facts=0 → judgement 不足 → 选错文档。

## 3. 实际修复（只动 1 个源文件 + 1 个测试文件）

**`src/enterprise_agent_kb/query_api.py`**：

1. 新增 `_definition_term_candidates(rewritten)` 辅助函数：对 definition query，
   从 `target_topic`/`aliases`/`should_terms`/`must_terms` 抽取实质中文术语（去标点、
   跳过纯拉丁、要求含 ≥2 字 CJK run、跳过"是什么"等噪声），返回去重候选。
2. `_inject_direct_term_definition_hits` 增加**中文长术语分支**：
   - 关键边界控制：`terms = [] if acronyms else _definition_term_candidates(rewritten)`——
     **仅当无短缩写时**才走术语匹配。短缩写（CP/CC）是更强信号，由 acronym 分支处理；
     术语分支专为"无缩写的中文定义查询"设计。这样既修复纯中文术语，又避免与缩写查询互相稀释。
   - 术语分支按 `object_value LIKE '%term%'` 匹配 `term_definition`/`concept_definition`，
     注入为 `direct_term_definition` channel hit。**评分优先权威字典术语**：去 markdown `**`
     后 `term` 字段以查询术语开头 → 3.6；含术语且 ≤40 字 → 3.2；含术语 → 3.0；否则 2.6。
3. 早返回条件改为 `if not acronyms and not terms`。

**`tests/test_mcp_server.py`**：移除 `test_mcp_server_tools_call_answer_query` 的
`@pytest.mark.xfail(strict=True)`（issue 已修复，断言不削弱即通过）。

## 4. 验证（全部勾选）

- [x] **复现验证**：`answer_query('什么是控制导引电路？')` 不再返回文档标题。
- [x] **期望行为**：返回权威字典定义 `控制导引电路 control pilot circuit: 设计用于电动汽车和供电设备之间信号传输或通信的电路。`（DOC-000003 FACT-013692），`answer_mode=definition`，`hit_count` 非零。
- [x] **xfail 解除**：`test_mcp_server_tools_call_answer_query` 由 xfail 转 pass（断言未削弱）。
- [x] **fast suite**：`680 passed, 1 skipped, 0 failed, 0 xfailed`（原 679+1xfail → 680+0）。
- [x] **check_health**：10/10 PASS；生产库 facts=7636 未变（修复只读 DB）。
- [x] **回归（短缩写定义查询）**：`CP控制导引是什么意思` 仍正确返回 `控制导引功能 control pilot function; CP: 用于监控电动汽车和供电设备之间交互的功能。`（边界控制生效，无回归）。
- [x] **集成 golden**：`test_definition_answer_for_control_pilot` + `test_agent_query_prefers_term_definition` 通过。

## 5. 顺手发现（不在本次范围，另记）

> `_choose_doc_from_routed_hits`（`answer_context_routing.py`）在无 `routing_summary` hit 时
> 回退 graph_candidates，**完全忽略实际召回 evidence/fact 所在文档**。本 issue 因 Fix A 让
> judgement sufficient（`_choose_doc_from_evidence_judgement` 第一优先级返回正确文档）而绕开。
> 但若将来出现"术语无权威定义、judgement 不足"的场景，graph 噪声仍可能选错文档。
> 不在本 issue 范围（analysis Fix B 标记为兜底，未实施），可后续另开 issue。

## 6. 影响面

仅 `query_api._inject_direct_term_definition_hits` 行为扩展（新增中文术语注入路径，
默认对无缩写的 definition query 生效）。未改 answer 主链路、未改 evidence_judge、
未改 `_extract_exact_terms`、未改 graph 兄弟扩展。符合 evidence-constrained：注入的是
KB 真实 term_definition fact（有 evidence 溯源），非 LLM 生成。

## 7. 到期条件核对

> report §8：当修复落地、`test_mcp_server_tools_call_answer_query` 在不削弱断言前提下通过时，
> 移除 xfail 并关闭 issue。

✅ 已满足。issue 可关闭。

## 8. 状态
status: fixed（issue 待 WP6 收口时关闭 acceptance）
