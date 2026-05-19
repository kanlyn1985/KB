---
doc_type: dev-guide
slug: query-chain-development-guide
component: query-chain
status: current
summary: 查询改写、召回、Graph 候选、证据裁判和答案策略的开发指南
tags:
  - query
  - retrieval
  - answer
  - graph
last_reviewed: 2026-05-19
---

# Query Chain Development Guide

## 概述

查询链路负责把用户问题转成可解释的候选集合，再经过证据裁判和答案策略输出结果。开发时必须保持一个边界：LLM 可以规划、扩写和裁判候选证据，但不能绕过规则校验直接决定最终事实。

## 前置依赖

- 工作目录：`E:\AI_Project\opencode_workspace\KB1`
- 知识库根目录：`knowledge_base`
- CLI：`C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base`
- 相关架构文档：`.codestable/architecture/query-chain-architecture.md`

## 快速上手

查看查询上下文：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base query-context --query "CP是什么意思" --limit 5
```

生成答案：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base answer-query --query "OBC输入过压怎么测" --limit 5
```

中文 HTTP 验证优先用 Python Unicode 字符串，避免 PowerShell here-string 把中文变成 `????`。

## 核心概念

| 概念 | 说明 |
|---|---|
| rewrite | 规则优先的查询归一化和 query_type 判定。 |
| expansion | LLM 辅助生成结构化检索计划，必须保留锚点并通过质量门。 |
| topic resolution | 把用户主题解析到 document、standard、term、process 等实体。 |
| graph candidates | Graph 给出的候选增强，不是最终事实裁决。 |
| evidence shape | 查询类型要求的证据结构，例如 definition、test_method、process_activity、timing。 |
| evidence judge | 在候选 fact/evidence ID 内判断证据是否足够。 |
| answer policy | 基于候选和 judge 结果组织答案模式。 |

## 模块入口

| 文件 | 责任 |
|---|---|
| `src/enterprise_agent_kb/query_rewrite.py` | 规则改写、query_type、锚点保护。 |
| `src/enterprise_agent_kb/query_expansion.py` | LLM 查询扩展和 fallback。 |
| `src/enterprise_agent_kb/advanced_query_planner.py` | 实验性三路 planner，默认关闭。 |
| `src/enterprise_agent_kb/query_api.py` | `build_query_context` 主入口。 |
| `src/enterprise_agent_kb/retrieval.py` | FTS、routing、rerank 和 retrieval run 记录。 |
| `src/enterprise_agent_kb/retrieval_router.py` | query_type 分通道召回、直接候选注入、过程 BP sibling 扩展。 |
| `src/enterprise_agent_kb/reranker.py` | 候选重排、对象锚点、负锚点和文档/内容级加权。 |
| `src/enterprise_agent_kb/retrieval_quality.py` | Recall/MRR/negative hit 等召回质量判定。 |
| `src/enterprise_agent_kb/evidence_judge.py` | 证据充分性和证据形状判定。 |
| `src/enterprise_agent_kb/answer_api.py` | 最终答案组装和澄清处理。 |
| `src/enterprise_agent_kb/query_ambiguity.py` | 短缩写和歧义澄清注册。 |

## 常见场景

### 修复查询失败

1. 用 `answer-query` 复现用户原问题。
2. 用 `query-context` 查看 `rewrite`、`retrieval_plan`、`topic_resolution`、`evidence_judgement`。
3. 判断根因属于入库缺失、召回 miss、rerank wrong、graph lost、judge wrong 还是 answer policy wrong。
4. 修复必须落在对应层，不能在答案层硬塞某个问题的特殊文本。
5. 加测试或 golden case，并更新本指南及相关架构文档。

### 证据裁判到答案的顺序约束

`evidence_judgement.best_fact_ids` 是已排序的事实候选约束。答案层选择 primary document 时必须优先使用第一个合法 best fact 所属文档，不能按文档数量多数投票覆盖 judge 的排序结果。否则会出现 judge 首位事实正确、answer policy 却被同名章节或跨文档噪声带偏的问题。

### Test Method 召回

`test_method_lookup` 不能只依赖通用 FTS topN。流程/试验步骤类 fact 容易被 “输入/过压/试验” 这类泛词稀释，因此 `query_api` 有 `direct_test_method` channel：按 `process_fact`、试验词、动作词和对象锚点注入候选，再交给 reranker 和 evidence judge。对象锚点必须区分内容级和文档级：候选内容命中 `车载充电机/OBC` 才给强加分，文件名只给弱提示；候选内容出现 `逆变/逆变器` 等负锚点且用户未询问逆变时要扣分。

### 判断 Graph 是否真的发挥作用

不要只看 `graph_hit_count`。有效判断标准是 Graph 候选是否进入最终 top context，并且 `rerank_explanations` 能说明 graph source 被保留。生命周期或过程活动查询必须从 process wiki/source facts 扩展到带 BP 锚点的 `process_fact`。

### 生命周期活动召回

生命周期/过程活动查询的目标证据形状是 `process_activity`，但实现上不能只认 `process_fact`。不同文档和解析器可能把同一 BP 活动抽成 `process_fact`，也可能保留为 BP 编号的 `table_requirement`。召回层必须把带 `SYS/SWE/SUP/... .BPn` 锚点的表格需求行当作过程活动候选，rerank 层再按 query_type、BP 编号、语言和焦点词排序。

BP sibling 扩展和多语言去重必须发生在候选截断前。否则 BP1 这类低分但必要的表格行可能在进入 rerank 前被 topN 截断。对同一 BP 的中英文重复项，去重不能只取原始分最高的候选；中文查询应优先保留中文命中和焦点词命中的候选，例如 `软件架构分析有哪些活动` 应优先保留包含 `分析软件架构` 的 `SWE.2.BP3` 中文证据。

### 参数意图召回

参数类查询除了对象锚点，还要识别值域/物理量意图。`CC电阻有哪些定义` 这类问题不能只因为候选带 `CC1/CC2` 或表级 `控制导引` 标签就进入 top context；候选必须同时符合 `电阻/阻值/Ω/Rn/resistance` 等电阻意图。这个约束放在 direct parameter candidate generation 和 reranker 两层，避免泛参数行、开关状态行或电容行挤掉真正的等效电阻证据。

英文缩写的符号匹配要区分大小写语义。全大写用户锚点 `CC` 不应匹配表格符号 `Cc`；否则连接确认问题会漂移到电容参数。

### Retrieval Quality 判定

`retrieval_quality` 的通过条件必须和 dashboard 指标一致。多个 `retrieval_must_hit` 锚点不能只靠 “至少命中一个且 rank<=5” 判定通过；默认 `min_recall_at_5=0.8`，可由 case 显式覆盖。失败归因中 `recall_at_5_below_threshold` 代表召回覆盖不足，不应通过降低阈值掩盖。

`negative_expected` 只检查用户可见证据内容，不能把内部候选标签或 snippet 前缀当作负样本命中，例如 `graph_fact table_requirement:` 里的 `table_requirement` 是内部类型标签，不是证据正文。负样本匹配不使用 token fallback，避免 `table_title` 和 `software requirements` 这类普通字段组合误判成 `table_requirement`。

### 处理短缩写问题

`CP是什么意思`、`CC是什么意思` 这类问题不能先让 LLM 猜。应先由 `query_ambiguity` 或规则层判定是否需要澄清；有上下文或参数问法时才进入 definition / parameter_meaning。

短缩写不能吞掉用户给出的上下文。`CP控制导引是什么意思`、`充电接口里的 CP 控制导引功能是什么意思` 这类“缩写 + 明确上下文 + 定义意图”必须保留复合主题，例如 `target_topic=CP控制导引`，不能归一化成裸 `CP`。裸缩写仍走澄清；带参数意图的 `CP占空比是什么意思`、`cp 9V PWM是什么意思` 仍走参数定义/参数含义。

普通定义问题的 evidence shape 应优先是 `term_definition`。只有问题文本本身包含 `阻值`、`电阻`、`电压`、`占空比`、`PWM`、`检测点`、`参数` 等参数意图时，`definition` 才允许 `parameter_definition` 作为可接受形状。这样可以防止术语定义问题被参数表或前言章节覆盖。

答案层的 section fallback 只能在没有强匹配术语定义时触发。强匹配不仅包括完全相同的中文/英文术语，也包括“复合主题里有缩写 + 上下文，而候选 term 同时包含该缩写和上下文”的情况，例如 `CP控制导引` 可以匹配 `控制导引功能 control pilot function; CP`。否则正确定义会被章节导言或标准替代信息覆盖。

## 测试

主回归：

```powershell
C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q
```

真实用户召回评测：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-user-query-retrieval-eval --suite regression:user_query_retrieval:current-code
```

局部短缩写回归：

```powershell
C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q -k "short_acronym or ambiguous"
```

## 已知限制与注意事项

- Advanced Query Planner 默认关闭，实验时设置 `EAKB_ENABLE_ADVANCED_QUERY_PLANNER=1`。
- 文本 LLM 调用顺序是 MiniMax primary、Astron backup。provider failure cooldown 必须按 provider + endpoint + model 隔离，不能让一次旧端点失败把新配置的 MiniMax 主力通道旁路掉。
- Evidence Judge 返回的 ID 必须来自候选集合。
- 无合法候选 ID 时不能判定 sufficient。
- 对单个 query 的修复必须先做失败归因，不能用后处理字符串替换掩盖召回或证据形状问题。

## 相关文档

- `.codestable/architecture/query-chain-architecture.md`
- `.codestable/architecture/closed-loop-architecture.md`
- `docs/dev/regression-eval-development-guide.md`
