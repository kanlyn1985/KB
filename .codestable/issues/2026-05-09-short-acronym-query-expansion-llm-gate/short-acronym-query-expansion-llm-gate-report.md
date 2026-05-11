---
doc_type: issue-report
issue: 2026-05-09-short-acronym-query-expansion-llm-gate
status: confirmed
severity: P1
summary: 短缩写定义查询在 query-context 入口会进入 LLM 扩写并导致慢查询或超时
tags:
  - query-chain
  - llm-gate
  - ambiguity
  - regression
---

# 短缩写定义查询进入 LLM 扩写 Issue Report

## 1. 问题现象

在按 CodeStable 新文档结构运行项目时，`query-context --query "CP是什么意思"` 曾在 60 秒左右超时。相同问题在 `answer-query --query "CP是什么意思"` 中可以返回澄清结果。

该现象说明不同入口对同一类短缩写定义问题的处理不一致：答案入口能提前澄清，调试/召回入口仍会继续进入完整查询链路。

## 2. 复现步骤

1. 在 `E:\AI_Project\opencode_workspace\KB1` 下运行：
   `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base query-context --query "CP是什么意思" --limit 3`
2. 观察到：命令执行时间异常长，曾触发超时。
3. 对照运行：
   `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base answer-query --query "CP是什么意思" --limit 3`
4. 观察到：答案入口直接返回 `clarification_required=true`。

复现频率：在 LLM 扩写可用但响应慢时稳定暴露；禁用 LLM 后 `build_query_context` 可正常返回。

## 3. 期望 vs 实际

**期望行为**：短缩写定义查询，如 `CP是什么意思`、`CC是什么意思`，应先走歧义澄清或规则回退；没有用户上下文时不应让 LLM 猜含义，也不应阻塞调试入口。

**实际行为**：`answer-query` 在答案层先做歧义拦截，但 `query-context` 仍会先进入 `query_expansion.expand_query()`，短缩写定义问题会调用 LLM 扩写。

## 4. 环境信息

- 涉及模块 / 功能：查询链路、LLM 查询扩写、歧义澄清、CLI/API 运行入口
- 相关文件 / 函数：
  - `src/enterprise_agent_kb/query_api.py::build_query_context`
  - `src/enterprise_agent_kb/query_expansion.py::expand_query`
  - `src/enterprise_agent_kb/answer_api.py::answer_query`
- 运行环境：Windows 本地开发环境，Python `C:\Python314\python.exe`
- 其他上下文：知识库根目录必须使用 `--root knowledge_base`；CLI 查询文本必须使用 `--query`

## 5. 严重程度

**P1** — 该问题会让查询调试入口和答案入口行为不一致，并可能让短缩写定义类问题进入不稳定的 LLM 扩写，违背“短缩写/歧义问题不能强行猜，要先让用户确认”的系统原则。

## 备注

本问题不是 CP 单点问题，而是“短缩写定义查询进入 LLM 扩写准入门”的框架问题。
