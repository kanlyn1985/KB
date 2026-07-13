---
doc_type: requirement
slug: requirement-resolver-overlay
pitch: 在 KB1 之上叠加客户/项目维度 OBC/DCDC 需求治理层，提供从需求包导入到 ECO 闭环的完整管线，默认关闭、opt-in 接入。
status: current
last_reviewed: 2026-07-13
implemented_by:
  - requirement-resolver-subsystem
tags:
  - requirement-resolver
  - overlay
  - customer-project
  - obc-dcdc
---

# Requirement Resolver 叠加子系统

## 愿景

为 KB1 增加客户/项目维度的需求治理能力：把标准、产品基线、客户通用、项目覆盖四级需求原子解析为有效需求，并支撑差异、冲突、合规、影响、审批、基线、发布门禁、ECO 全生命周期治理。

## 核心约束

- 叠加层不替代 KB1 证据约束答案链，仅在显式启用时通过软路由回答需求类查询。
- 解析器确定性，不让 LLM 决定有效需求值（evidence_judge 仍是唯一事实裁决边界）。
- 28 张 requirement_* 表 IF NOT EXISTS，不与 KB1 既有 30 表冲突。
- query_api/retrieval/evidence_judge 零改动；answer_api 仅 +6 行软路由守卫。

## 能力清单

需求包导入 -> 候选抽取（规则优先半自动）-> 人工评审提升 -> Profile 继承 -> 有效需求解析 -> 差异/冲突扫描 -> 合规矩阵 -> 影响分析 -> 审批治理 -> 基线冻结 -> 版本对比/漂移 -> DV/PV/SOP 发布门禁 -> ECO 工程变更闭环。

## 接入方式

- CLI：`eakb requirement <subaction>`（38 子动作）
- answer_api 软路由：`EAKB_ENABLE_REQUIREMENT_ROUTER=1`（默认关闭）
- api_server：框架中性 handler + 可选 FastAPI router

## 技术债

1. schema 待迁移到 migrations/0xx_requirement_program.sql
2. ECO/基线/审批跨表事务待收敛
3. API 适配器双路径待选择唯一集成路径
