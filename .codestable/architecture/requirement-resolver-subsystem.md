---
doc_type: architecture
slug: requirement-resolver-subsystem
status: current
last_reviewed: 2026-07-13
summary: Requirement Resolver 叠加子系统架构（客户/项目维度需求治理）
tags:
  - kb1
  - architecture
  - requirement-resolver
  - overlay
---

# Requirement Resolver 子系统架构

> 状态：已合并（feature/requirement-resolver）
> 创建日期：2026-07-13
> 最近审计：2026-07-13

## 1. 定位

Requirement Resolver 是叠加在 KB1 之上的客户/项目维度 OBC/DCDC 需求治理子系统。它不替代 KB1 的证据约束答案链，而是作为独立的需求维度治理层，仅在显式启用时通过软路由回答需求类查询。

## 2. 数据模型

28 张 requirement_* 表，全部 CREATE TABLE IF NOT EXISTS，与 KB1 既有 30 表无命名冲突。按治理阶段分组：客户/项目、需求原子与变体、有效需求、证据与测试、审批、候选、基线、发布门禁、ECO。

### 2.1 Schema 迁移机制（Phase 2，2026-07-13）

schema 真相源已从 `requirements/schema.py` SCHEMA_SQL 迁移到 `migrations/002_requirement_program.sql`，复用 KB1 `PRAGMA user_version` 机制（与 `001_expected_points.sql` 共享同一 user_version 序列）。`repository.initialize_schema()` 调用 `apply_pending_migrations`；SCHEMA_SQL 保留为 fallback 镜像（`TestSchemaSqlMirror` 断言两源表集一致）。详见 `docs/requirement-program/SCHEMA_MIGRATION_STRATEGY.md`。

详见 docs/kb1_requirement_program_review.html §3。

## 3. 三个集成点

1. **CLI 子命令族**（cli/_requirement.py）：遵循 KB1 模块化 register_subcommand + handle_command 模式，在 _orchestrator.py 注册。eakb requirement <subaction> 暴露 38 个子动作。
2. **answer_api 软路由**（默认关闭）：EAKB_ENABLE_REQUIREMENT_ROUTER=1 启用。仅在 requirement_effective/requirement_diff/requirement_conflict_scan 三种意图且 confidence>=0.75 时介入，否则返回 None，既有答案链不变。
3. **api_server FastAPI 适配**（可选）：框架中性 handler + 可选 FastAPI router。

## 4. KB1 边界兼容性

- 解析器确定性，不让 LLM 决定有效需求值（evidence_judge 仍是唯一事实裁决边界）。
- query_api/retrieval/evidence_judge 零改动；answer_api 仅 +6 行软路由守卫。
- 软路由默认关闭，回退到既有答案链（含降级）。
- 无新向量库/分布式服务，使用 SQLite。

## 5. 已知技术债

1. ~~schema 定义在 requirements/schema.py SCHEMA_SQL，待迁移到 migrations/0xx_requirement_program.sql。~~ **已解决（Phase 2）**：已迁移到 `migrations/002_requirement_program.sql`，复用 KB1 user_version 机制。SCHEMA_SQL 保留为 fallback 镜像。
2. ~~ECO/基线/审批跨表操作需服务级事务收敛（Phase 3 目标）。~~ **已解决（Phase 3）**：Repository 新增 `transaction()` 上下文管理器 + `_TxnConnectionProxy` 代理，ECO 的 submit/approve/apply/close 四个跨服务方法用单事务包裹；Approval 状态机（submitted 唯一可转换态）+ Baseline freeze 事务（重复 ID 回滚）。59 个 `closing(self.connection())` 调用替换为 `self._conn_ctx()`，在事务激活时复用代理连接，内部 `commit()`/`close()` 变 no-op。
3. API 适配器双路径（handler + FastAPI router）待选择唯一集成路径。

## 6. 爆炸半径

- answer_api.py: +6 行（1 import + 5 行软路由守卫）
- cli/_orchestrator.py: +3 行（1 import + 1 register + 1 handle）
- cli/_requirement.py: 32 行新适配器
- requirements/: 21 模块 6559 LOC（完全隔离）
- migrations/002_requirement_program.sql: 28 表 + 25 索引（Phase 2）
- tests/requirement/: 27 测试文件 95 测试（含 10 个 schema migration 测试 + 7 个 approval 状态机测试 + 3 个 baseline 事务测试 + 3 个 ECO 事务边界测试）
