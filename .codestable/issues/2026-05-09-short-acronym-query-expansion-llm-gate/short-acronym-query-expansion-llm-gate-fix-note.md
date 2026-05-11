---
doc_type: issue-fix
issue: 2026-05-09-short-acronym-query-expansion-llm-gate
status: fixed
strategy: query-expansion-rule-gate
related:
  - short-acronym-query-expansion-llm-gate-report.md
  - short-acronym-query-expansion-llm-gate-analysis.md
tags:
  - query-expansion
  - regression
  - llm-boundary
  - codestable
---

# 短缩写定义查询进入 LLM 扩写 Fix Note

## 1. 修复范围

本次修复只处理“短缩写定义查询进入 LLM 扩写准入门”的根因，不改变召回排序、答案生成、PDF 解析或 graph 构建逻辑。

修改文件：

- `src/enterprise_agent_kb/query_expansion.py`
- `tests/test_query_repair_regression.py`
- `.codestable/attention.md`
- `.codestable/architecture/ARCHITECTURE.md`

## 2. 实际修改

### 2.1 LLM 扩写准入门

在 `src/enterprise_agent_kb/query_expansion.py:162` 的 `_should_use_rule_expansion()` 中增加短缩写定义查询判断。

新增规则：

- 匹配 `[A-Z]{1,6}\d*`
- 匹配定义类问法：`是什么意思`、`什么是`、`定义是什么`、`含义是什么`、`代表什么意思`、`表示什么`
- 命中后直接走 `_fallback_expansion()`，不调用 LLM

新增函数位置：

- `src/enterprise_agent_kb/query_expansion.py:176`

### 2.2 回归测试

在 `tests/test_query_repair_regression.py:237` 新增测试：

- monkeypatch LLM 调用为直接失败
- 调用 `expand_query("CP是什么意思")`
- 断言 `used_llm is False`
- 断言答案形状为 `definition`
- 断言硬锚点保留为 `CP`

### 2.3 CodeStable 运行文档

在 `.codestable/attention.md` 补充：

- 工作目录
- `--root knowledge_base`
- API 启动命令
- `/health` 健康检查
- `query-context` / `answer-query` 必须使用 `--query`
- PowerShell 中文编码风险
- 短缩写定义问题不应先交给 LLM 扩写

在 `.codestable/architecture/ARCHITECTURE.md` 补充：

- 核心概念
- 四个闭环相关模块索引
- LLM 边界和短缩写歧义规则
- 单机运行和路径约束

## 3. 验证结果

### 3.1 针对性回归

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q -k "short_acronym or ambiguous_cp or ambiguous_cc or short_cc_definition"`

结果：

`6 passed, 46 deselected`

### 3.2 完整查询修复回归文件

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q`

结果：

`29 passed, 23 deselected`

### 3.3 CLI 状态检查

命令：

`C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base status`

结果：

- workspace 存在
- SQLite 数据库存在
- `source_units`、`retrieval_runs`、`golden_cases`、`eval_runs`、`eval_results` 等闭环表存在

### 3.4 API 运行检查

服务已重启：

`http://127.0.0.1:8000`

健康检查：

`GET /health` 返回 `status=ok`

### 3.5 HTTP 查询验证

`POST /query-context`，query=`CP是什么意思`：

- `hit_count=3`
- `query_expansion.used_llm=false`
- first hit: `FACT-113166`
- first topic: `控制导引功能 control pilot function; CP`

`POST /answer-query`，query=`OBC输入过压怎么测`：

- `answer_mode=test_method_lookup`
- `confidence=0.93`
- first fact: `FACT-116907`
- evidence judgement sufficient: `true`
- direct answer 不含 `&nbsp;`

## 4. 影响面回归

- `answer-query CP是什么意思` 仍返回澄清选项，不受影响。
- `query-context CP是什么意思` 不再进入 LLM 扩写超时。
- `OBC输入过压怎么测` 仍能召回试验方法，不受短缩写规则影响。
- 规则是通用短缩写定义准入门，不是 CP 单点硬编码。

## 5. 顺手发现

- `query-context CP是什么意思` 虽然不再调用 LLM，但仍会返回召回上下文而不是 clarification context；是否要让底层 query context 也短路为 clarification，需要单独定义接口语义后再做。
- 部分 supporting evidence 原始片段仍可能保留 HTML 渲染残留；当前验证只确认 direct answer 已清洗。该问题属于 evidence 展示/清洗链路，需另开 issue 处理。
- 当前闭环 dashboard 仍显示 ingestion / retrieval / answer / regression 有 warn 或 fail，这不是本次修复范围。

## 6. 结论

本次修复完成了短缩写定义查询的 LLM 扩写准入门约束，避免 query-context 入口在无上下文缩写问题上直接调用 LLM。修复符合“LLM 不能直接决定最终事实，短缩写/歧义问题不能强行猜”的架构原则。
