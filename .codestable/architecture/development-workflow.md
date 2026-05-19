---
doc_type: architecture
slug: development-workflow
status: current
last_reviewed: 2026-05-09
implements: []
tags:
  - codestable
  - workflow
  - development
---

# CodeStable 开发流程架构

## 文档分层

```mermaid
flowchart TD
  REQ["requirements: 为什么要有这个能力"] --> ROAD["roadmap: 大能力怎么拆"]
  ROAD --> FEAT["features: 单个能力怎么实现和验收"]
  FEAT --> ARCH["architecture: 已落地现状"]
  ISSUE["issues: 问题报告、根因、修复记录"] --> ARCH
  FEAT --> GUIDE["docs/dev and docs/user: 对外指南"]
  ISSUE --> COMP["compound: learning / decision / trick / explore"]
```

## 标准开发路径

```mermaid
flowchart LR
  V["requirement"] --> R["roadmap when scope is large"]
  R --> D["feature design"]
  D --> C["checklist"]
  C --> I["implementation"]
  I --> A["acceptance"]
  A --> AR["architecture / req / guide backfill"]
```

## 问题修复路径

```mermaid
flowchart LR
  REP["issue report"] --> ANA["root cause analysis"]
  ANA --> FIX["fix note + tests"]
  FIX --> LEARN["optional learning / decision"]
```

## 本项目硬约束

- 所有 CodeStable 子技能先读 `.codestable/attention.md`。
- 代码变更必须先找根因，再决定修复层级。
- 不把局部失败点当作唯一输入，优先修框架边界。
- 不移动旧 `docs/` 历史文档；新开发流程文档写入 `.codestable/` 和 `docs/dev/`。
