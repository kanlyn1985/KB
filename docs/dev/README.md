---
doc_type: dev-guide
slug: dev-docs-index
component: docs
status: current
summary: KB1 开发者文档入口和模块指南索引
tags:
  - docs
  - development
last_reviewed: 2026-05-12
---

# KB1 Developer Docs Index

## 概述

本目录是面向开发者的可发布指南入口。`.codestable/` 记录需求、方案、验收和决策；`docs/dev/` 说明开发者如何运行、调试、扩展和验证系统。

## 文档入口

| 指南 | 适用场景 |
|---|---|
| `kb1-development-guide.md` | 新开发者第一次进入项目，了解运行、测试和文档流程。 |
| `query-chain-development-guide.md` | 修改查询改写、召回、Graph 候选、证据裁判或答案策略。 |
| `ingestion-coverage-development-guide.md` | 修改文档入库、source units、coverage 映射或覆盖缺口闭合。 |
| `regression-eval-development-guide.md` | 修改 golden cases、eval runs、failure analysis 或回归 dashboard。 |
| `derived-state-governance-development-guide.md` | 修改 FTS、workspace doctor、rebuild、run hygiene 或残留治理。 |
| `api-cli-development-guide.md` | 修改 CLI、API server、Workbench 数据出口或本地运行方式。 |
| `project-organization-review.md` | 当前工作区整理、变更归类、生成物处理和后续提交收敛。 |

## 文档同步规则

每一步开发都必须同步更新文档：

1. 代码改动完成后，核对 `.codestable` 中对应的 architecture、requirement、roadmap、feature 或 issue。
2. 行为、接口、命令、开发流程或用户操作变化时，更新 `docs/dev` 或 `docs/user`。
3. 新增模块级能力时，优先更新既有模块指南；只有读者或主题边界明显不同，才新增 guide。
4. 文档修改后运行 frontmatter 校验。

## 校验

单个 guide：

```powershell
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/query-chain-development-guide.md --require doc_type --require status
```

全部当前 guide：

```powershell
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/README.md --require doc_type --require status
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/kb1-development-guide.md --require doc_type --require status
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/query-chain-development-guide.md --require doc_type --require status
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/ingestion-coverage-development-guide.md --require doc_type --require status
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/regression-eval-development-guide.md --require doc_type --require status
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/derived-state-governance-development-guide.md --require doc_type --require status
C:\Python314\python.exe .codestable/tools/validate-yaml.py --file docs/dev/api-cli-development-guide.md --require doc_type --require status
```

## 已知边界

旧 `docs/` 根目录中保留了历史记录和交付笔记，很多文件没有 frontmatter，不作为当前开发指南体系的一部分。当前规范入口以本索引和 `docs/dev/*.md` 的 `status: current` 文件为准。
