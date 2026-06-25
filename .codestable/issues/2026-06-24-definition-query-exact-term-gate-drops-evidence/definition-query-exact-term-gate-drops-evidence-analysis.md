# definition-query-exact-term-gate-drops-evidence — Analysis（修订）

> Issue analysis (Sprint 2 WP2)。本文**修订并取代** report 第 3/4 节的根因判断——
> report 假设 `exact_terms=["控制导引电路"]` 触发了 answer 层 gate 清零，实测**不成立**。
> 本分析基于 2026-06-25 的实际运行时追踪，定位到**真正的两级缺陷**。

## 1. 现象（复现，与 report 一致）

查询 `什么是控制导引电路？`：
- `answer_query` 返回 `direct_answer='中华人民共和国国家标准：GB/T 18487.4—2025'`（文档标题），`answer_mode=definition`，`hit_count=0`。
- `build_query_context` 单独返回 `hit_count=4, evidence=4（全在 DOC-000012）, facts=0`。

## 2. 修订根因（运行时追踪）

### 2.1 report 的"exact-term gate 清零"假设——**不成立**

`_extract_exact_terms(query)`（`answer_query_parsing.py:71`）正则 `[A-Z][A-Z0-9/-]{1,}` **只匹配纯拉丁大写 token**。
查询 `什么是控制导引电路？` 是纯中文 → `exact_terms=[]`。

因此 `answer_api.py` `_resolve_intent_and_context` 里的 `if exact_terms and ...` gate **被整个跳过**，
`_should_block_unconstrained_answer`（`exact_terms` 为空直接 return False）、
comparison gate（query_type=definition 非 comparison）都不触发。**answer 层 gate 没有清零上下文。**

### 2.2 真正清零的地方：primary doc 选错 + restrict 过滤

`_resolve_intent_and_context` 末尾调用 `_choose_primary_doc_id` → 返回 **DOC-000016**，
随后 `_restrict_context_to_doc(ctx, DOC-000016)` 把 hits/evidence/facts 过滤成只剩 DOC-000016 的，
而 4 条 evidence 全在 **DOC-000012** → 过滤后 `evidence=0, facts=0` → 空上下文 → 降级回填文档标题。

### 2.3 为什么选了 DOC-000016（而不是正确的 DOC-000003 / DOC-000012）

`_choose_primary_doc_id`（`answer_context_routing.py:17`）顺序：
1. `_choose_doc_from_evidence_judgement` → **None**（judgement.sufficient=False，best_fact_ids 为空）
2. `_choose_doc_from_routed_hits` → **DOC-000016**（命中此分支）
3. `_choose_doc_by_phrase_match` → 本会是 **DOC-000003**（正确文档，含权威 term_definition），但没走到

`_choose_doc_from_routed_hits` → `_query_specific_doc_hits`：只要 `routing_summary`/`graph` channel 的 hit。
本查询没有 routing_summary hit，于是**回退到 `context.graph_candidates`**——而 graph_candidates 有 16 条全是 **DOC-000016**
（`has_process` 兄弟扩展，score 0.686），按 count+score 投票胜出 → 错选 DOC-000016。

**问题核心**：定义类查询的主文档选择**只看 graph/routing 信号，完全忽略实际召回的 evidence/fact 文档**（DOC-000012 有 4 条 evidence 却零权重）。

### 2.4 召回层缺陷：权威 term_definition 没注入 facts

权威定义在 **DOC-000003**（`FACT-013692`，`term="**控制导引电路 control pilot circuit**"`）。
但召回层 `facts=0`：`_inject_direct_term_definition_hits`（`query_api.py:747`）只处理
`_short_definition_acronyms`（纯拉丁 `[A-Z]{2,6}`）→ 中文长术语返回空 → 不注入任何 term_definition。
叠加 2.2，即使 DOC-000003 是正确文档也没机会被选中。

## 3. 三个正确信号 vs 实际选择

| 信号 | 指向 | 是否被采纳 |
|---|---|---|
| 权威 term_definition fact（FACT-013692） | **DOC-000003** | ✗ 未注入 facts |
| `_choose_doc_by_phrase_match` | **DOC-000003** | ✗ 未走到（被 routed_hits 拦截） |
| 实际召回 evidence | DOC-000012 | ✗ 被 restrict 过滤 |
| graph_candidates 兄弟扩展 | DOC-000016 | ✓ **被采纳（错误）** |

## 4. 推荐修复方案（最小、定义路径专属、不动 answer 主链路）

**方案 = 召回层根因修复（注入中文长术语的 term_definition hit）+ 选择层兜底修正**

### Fix A（根因，召回层）：`_inject_direct_term_definition_hits` 支持中文长术语
当 `rewritten.query_type == "definition"` 且存在实质性中文/非缩写术语（来自 `target_topic`/`aliases`/`should_terms`，去掉标点）时，
按 term 文本（归一化去掉 `**` markdown 包裹）匹配 `term_definition`/`concept_definition` facts，注入为 `direct_term_definition` channel hit（高分，如 3.0，置于顶部）。
- 效果：DOC-000003 的 FACT-013692 被注入 → facts 非空 → judgement sufficient → `_choose_doc_from_evidence_judgement` 返回 **DOC-000003**（正确文档，第一优先级，不再走到 routed_hits）。
- 边界：注入的是 KB 真实 fact（有 evidence 溯源），符合 evidence-constrained；只对 definition query 生效。

### Fix B（兜底，选择层）：`_choose_doc_from_routed_hits` 不应忽略实际 evidence 文档
当没有 `routing_summary` hit、只能回退 graph_candidates 时，**若上下文已有实际召回的 evidence/fact 命中**，
优先按 evidence 命中的 doc 投票，而不是纯 graph_candidates。
- 这是双保险：即使 Fix A 没注入 facts，也不会因为 graph 噪声把真实 evidence 文档选没。

### 不做的（范围外）
- 不改 `_extract_exact_terms`（它只识别拉丁缩写是设计如此，改它会影响所有 query_type 的 gate）。
- 不重写 `_choose_primary_doc_id` 主链路。
- 不动 graph 兄弟扩展逻辑（它是其它查询的正确行为）。

## 5. 验证

- [ ] `answer_query('什么是控制导引电路？')` 返回包含"控制导引电路"术语定义的答案（非文档标题）。
- [ ] `answer_query` 的 evidence/facts 非空，primary doc = DOC-000003。
- [ ] 去掉 `test_mcp_server_tools_call_answer_query` 的 xfail，**不削弱断言**即通过。
- [ ] fast suite 仍 0 failed；不新增 xfail。
- [ ] 影响面回归：其它 definition 查询（短缩写 CP/CC、其它中文术语）不退化。

## 6. 状态
status: fixed（2026-06-25 WP2 修复落地，见 -fix-note.md；issue 待 WP6 收口关闭）
