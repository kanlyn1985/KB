# KB1 Requirement Resolver 下一阶段开发计划

## 当前状态

Requirement Resolver 已完成第一阶段闭环：

- 客户/项目需求模型
- Profile 继承与有效需求解析
- 差异与冲突分析
- Compliance Matrix
- Impact Analysis
- Approval Governance
- Candidate Extraction
- Requirement Package Import
- Baseline Versioning
- Release Gate
- ECO Workflow

下一阶段不再继续增加孤立功能，重点转向工程化收敛。

---

# Phase 1：验证链修复（最高优先级）

目标：让代码、测试、审计、CI 完全一致。

任务：

1. 修复测试目录约定

统一：

```
tests/requirement/
```

修改：

- run_requirement_program.py
- audit_requirement_program.py

使用递归发现：

```
pytest/unittest discover -s tests/requirement
```

2. 补齐集成脚本

确认：

```
scripts/apply_requirement_cli_integration.py
scripts/apply_requirement_answer_api_integration.py
scripts/apply_requirement_api_integration.py
```

必须存在并保持幂等。

3. 增加 GitHub Actions

自动执行：

```
unit tests
requirement audit
smoke validation
```

---

# Phase 2：Schema Migration 化

当前 schema.py 内 SQL 已满足 MVP，但长期维护需要迁移。

目标：

```
requirements/schema.py
        ↓
migrations/
        ↓
schema version tracking
```

新增：

```
schema_migrations
```

要求：

- 可升级
- 可审计
- 可回滚
- 不破坏 KB1 原有表

---

# Phase 3：事务模型强化

重点模块：

## ECO

当前流程：

```
create
→ approve
→ apply
→ baseline
→ release gate
```

升级为单事务边界。

## Approval

增加：

- 状态机
- 并发保护
- 审批事件完整链

## Baseline

增加：

- freeze transaction
- rollback checkpoint
- version compare

---

# Phase 4：真实企业数据接入

从 sample data 进入真实输入：

```
客户规格书 PDF
需求Excel
测试报告
变更通知
```

流程：

```
Document
 ↓
OCR/Parser
 ↓
Candidate Requirement
 ↓
Review
 ↓
Profile Variant
```

原则：

LLM 只能生成候选，不直接改变有效需求。

---

# Phase 5：知识图谱融合

Requirement Resolver 与 KB1 Graph 融合：

新增关系：

```
Requirement
 ├── supported_by Evidence
 ├── verified_by TestResult
 ├── impacts Component
 ├── changed_by ECO
 └── approved_by User
```

目标：形成工程知识网络。

---

# Phase 6：生产化

包含：

- RBAC
- Audit Log
- Multi Project Isolation
- API Versioning
- Dashboard
- Release Management

---

# 验证原则

后续每个阶段必须满足：

```
代码修改
 ↓
单元测试
 ↓
Smoke Test
 ↓
Audit
 ↓
GitHub Actions
 ↓
Merge
```

不再只增加代码，而是保持系统闭环。
