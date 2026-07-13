# Requirement Program Schema 迁移策略

## 1. 当前状态

Requirement Program 当前把 schema 定义放在：

```text
src/enterprise_agent_kb/requirements/schema.py
```

其中 `SCHEMA_SQL` 以 `CREATE TABLE IF NOT EXISTS` 方式创建 requirement 子系统表。

这适合 MVP 和独立验证，但正式长期维护应迁移到项目统一 migration 机制。

## 2. 推荐迁移方向

建议新增：

```text
migrations/
  0xx_requirement_core.sql
  0xy_requirement_compliance.sql
  0xz_requirement_governance.sql
  0xa_requirement_baseline_release_eco.sql
```

或者：

```text
src/enterprise_agent_kb/migrations/
  0xx_requirement_program.sql
```

取决于现有仓库最终采用的 migration 目录约定。

## 3. 建议拆分

### 3.1 Core

```text
customers
customer_projects
requirement_atoms
requirement_profiles
requirement_profile_inheritance
requirement_variants
requirement_overrides
effective_requirements
requirement_evidence_bindings
```

### 3.2 Verification

```text
requirement_test_methods
requirement_test_cases
requirement_test_results
```

### 3.3 Governance

```text
requirement_approvals
requirement_approval_events
requirement_candidate_batches
requirement_candidates
requirement_candidate_events
requirement_import_packages
```

### 3.4 Baseline / Gate / ECO

```text
requirement_baselines
requirement_baseline_items
requirement_baseline_events
requirement_release_gate_runs
requirement_release_gate_findings
requirement_eco_orders
requirement_eco_actions
requirement_eco_events
```

## 4. Schema version table

建议增加：

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);
```

如果项目已有 migration 表，则复用已有表。

## 5. 兼容原则

1. 只做 additive migration。
2. 不 drop 旧表。
3. 不重命名已有列。
4. enum 使用 TEXT，不做硬约束，避免 SQLite 迁移复杂化。
5. 新增索引必须使用 `IF NOT EXISTS`。
6. 所有 derived table 必须可重建。

## 6. 回滚策略

SQLite 下不建议自动 drop 表回滚。推荐：

```text
代码回滚
  + 停止写入新表
  + 保留数据
  + 后续人工 archive
```

对于开发环境可以提供：

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement reset-requirement-data --confirm
```

但生产环境不应提供无保护删除。
