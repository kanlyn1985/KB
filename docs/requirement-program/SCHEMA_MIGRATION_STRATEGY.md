# Requirement Program Schema 迁移策略

## 1. 当前状态（Phase 2 已实施，2026-07-13）

Requirement Program 的 schema 已从模块级 SQL 迁移到 KB1 统一 migration 机制：

```text
src/enterprise_agent_kb/requirements/schema.py        # SCHEMA_SQL 保留为 fallback 镜像
src/enterprise_agent_kb/migrations/002_requirement_program.sql   # 真相源（28 表 + 25 索引）
```

`repository.initialize_schema()` 改为调用 KB1 的 `apply_pending_migrations(connection, migrations_dir)`，
复用 `PRAGMA user_version` 版本追踪（与 `001_expected_points.sql` 共享同一 user_version 序列）。

### 1.1 关键决策

- **复用 KB1 user_version 机制**（不新增 schema_migrations 表）：requirement 子系统 28 张表与
  KB1 主线 30 张表共用同一个 knowledge.db 和 user_version 序列。002 迁移在 user_version >= 2 时跳过。
- **单文件迁移**（不拆分 core/verification/governance/baseline 多文件）：28 张表作为一个原子迁移单元，
  降低迁移管理复杂度。后续如需增量 schema 变更，新增 `003_*.sql`、`004_*.sql`。
- **SCHEMA_SQL 保留为 fallback 镜像**：migrations 目录找不到时（如某些打包布局）回退到 executescript。
  `tests/requirement/test_schema_migration.py::TestSchemaSqlMirror` 断言两源表集一致。

### 1.2 兼容性

- `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` 保证幂等。
- 已有 requirement 表的 DB（如 smoke 测试临时 workspace）重复执行 init-schema 安全。
- 生产 DB（user_version=1，无 requirement 表）升级到 2，保留原有 KB1 表（documents 等）。
- 新 workspace：`requirement init-schema` 顺带应用 001_expected_points（无害，幂等）。

## 2. 迁移文件

```text
src/enterprise_agent_kb/migrations/002_requirement_program.sql
```

包含 28 张表（与 schema.py SCHEMA_SQL 完全一致）：

- Core: customers, customer_projects, requirement_atoms, requirement_profiles,
  requirement_profile_inheritance, requirement_variants, requirement_overrides,
  effective_requirements, requirement_evidence_bindings
- Verification: requirement_test_methods, requirement_test_cases, requirement_test_results
- Governance: requirement_approvals, requirement_approval_events, requirement_candidate_batches,
  requirement_candidates, requirement_candidate_events, requirement_import_packages,
  requirement_import_events, requirement_resolution_runs
- Baseline/Gate/ECO: requirement_baselines, requirement_baseline_items, requirement_baseline_events,
  requirement_release_gate_runs, requirement_release_gate_findings, requirement_eco_orders,
  requirement_eco_actions, requirement_eco_events

## 3. Schema version 追踪

采用 KB1 既有的 `PRAGMA user_version` 机制（不新增 schema_migrations 表）：

| user_version | 含义 |
|---|---|
| 0 | 全新 DB，未应用任何迁移 |
| 1 | 001_expected_points.sql 已应用（expected_points 表） |
| 2 | 002_requirement_program.sql 已应用（28 张 requirement_* 表） |

`apply_pending_migrations` 按版本号顺序应用 `version > current` 的迁移，每个迁移独立事务，
失败时停留在最后成功的版本。

## 4. 后续增量迁移

若需要修改 requirement schema（加列、加索引、加表），新增：

```text
src/enterprise_agent_kb/migrations/003_<descriptive_name>.sql
```

遵循原则：
1. 只做 additive migration（加列、加表、加索引）。
2. 不 drop 旧表，不重命名已有列。
3. enum 使用 TEXT，不做硬约束。
4. 新增索引必须使用 `IF NOT EXISTS`。

## 5. 验证

- `tests/requirement/test_schema_migration.py`（10 个测试）：迁移文件存在性、表完整性、
  幂等性、user_version 升级、SCHEMA_SQL 镜像一致性。
- `scripts/audit_requirement_program.py` 新增 `migration.file` 检查（12/12 PASSED）。
- `scripts/run_requirement_program.py --mode smoke`：17/17 gate 通过。

## 6. 回滚策略

SQLite 下不自动 drop 表回滚。推荐：

```text
代码回滚
  + 停止写入新表
  + 保留数据
  + 后续人工 archive
```

开发环境可重建 workspace；生产环境不提供无保护删除。
