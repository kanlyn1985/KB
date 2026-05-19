---
doc_type: feature-design
feature: 2026-05-09-codestable-development-docs
status: approved
summary: 补齐 KB1 在 CodeStable 新结构下的开发流程文档
roadmap: kb1-four-loop-hardening
roadmap_item: codestable-development-docs
tags:
  - documentation
  - codestable
  - development-flow
---

# CodeStable 开发文档补齐 Design

## 1. 目标

把 KB1 的当前工程事实沉淀到 CodeStable 新结构，让后续开发可以按 requirement → roadmap → feature/issue → architecture → guide 的路径追踪，不再只依赖分散的历史 `docs/`。

## 2. 明确不做

- 不移动旧 `docs/` 历史文档。
- 不修改业务代码。
- 不创造未实现能力。
- 不把 roadmap 的计划内容写进 architecture 现状文档。

## 3. 产物

- `.codestable/requirements/VISION.md`
- `.codestable/requirements/*.md`
- `.codestable/architecture/*-*.md`
- `.codestable/roadmap/kb1-four-loop-hardening/*`
- `.codestable/features/2026-05-09-codestable-development-docs/*`
- `docs/dev/kb1-development-guide.md`

## 4. 验收场景

- 开发者能从 VISION 看到 KB1 当前四个核心能力。
- 开发者能从 roadmap 看到下一步开发拆解。
- 开发者能从 feature acceptance 看到本次文档补齐是否完成。
- 开发者能从 dev guide 运行项目、启动 API、跑测试和理解六闭环。

## 5. 风险

- 历史 `docs/` 内容很多，当前只做索引和新结构补齐，不做批量迁移。
- 文档描述必须以当前代码和已验证运行命令为准，避免写未来态。
