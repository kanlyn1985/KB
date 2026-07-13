# Requirement Program 系统级收敛与集成审计

## 1. 审计目标

本审计不是新增业务功能，而是判断 Requirement Resolver 集成包是否具备进入真实仓库合并阶段的工程条件。

审计范围覆盖：

1. 代码结构是否清晰、可维护。
2. schema 是否完整、可增量落地。
3. CLI / answer soft-router / API adapter 是否具备低侵入集成方式。
4. 自动化验证是否覆盖主业务闭环。
5. 是否存在合并前必须处理的阻断项。
6. 是否存在可以接受但需要后续治理的技术债。

## 2. 当前系统闭环

当前 requirement program 已覆盖以下链路：

```text
客户项目需求包导入
  → 候选需求抽取
  → 人工 review / promote
  → 客户 / 项目 profile
  → 最终有效需求解析
  → 差异与冲突扫描
  → 测试覆盖与合规矩阵
  → 客户需求变更影响分析
  → 审批治理
  → 项目需求基线冻结
  → 基线版本比较
  → 漂移检测
  → DV/PV/SOP 发布门禁
  → ECO 工程变更闭环
  → 自动验证报告
```

这个范围已经不是单纯 RAG 能力，而是一个客户定制化产品需求治理子系统。

## 3. 合并前门禁

建议合并前必须通过以下门禁：

| 门禁 | 是否阻断 | 说明 |
|---|---:|---|
| Python 语法解析 | 是 | 所有新增 Python 文件必须可 parse。 |
| 单元测试 | 是 | `python -m unittest discover -s tests -v` 必须通过。 |
| Orchestrator smoke | 是 | `scripts/run_requirement_program.py --mode smoke` 必须通过。 |
| schema 表完整性 | 是 | 所有 requirement_* 表必须存在。 |
| integration 脚本幂等性 | 是 | 重复运行不得重复插入代码。 |
| answer router 默认关闭 | 是 | 未设置环境变量时不得劫持现有 answer_api。 |
| API integration 安全拒绝 | 是 | 无法识别 FastAPI 形态时必须拒绝自动修改。 |
| 文档与命令一致性 | 否 | 不阻断，但必须记录。 |
| 模块体积 | 否 | 超大模块可以后续拆分。 |

## 4. 已知风险

### 4.1 schema 目前采用模块内 SQL 常量

当前 MVP 为降低落地成本，把 requirement schema 放在 `requirements/schema.py`。这适合早期扩展，但长期应迁移到正式 migration 体系。

建议下一阶段处理：

```text
src/enterprise_agent_kb/requirements/schema.py
  → migrations/0xx_requirement_program.sql
  → migration registry / schema version table
```

### 4.2 repository 层事务边界需要进一步收敛

当前多个服务模块直接使用 repository 方法组合业务流程。ECO、baseline、approval 等跨表操作应最终收敛到显式 transaction。

推荐原则：

```text
单表写入：repository method
跨表业务闭环：service-level transaction
```

### 4.3 API adapter 是框架无关实现

`requirements/api.py` 同时提供 framework-independent handler 和 optional FastAPI router。这是合理的兼容策略，但正式仓库合并后应根据真实 `api_server` 结构选择唯一集成路径。

### 4.4 extraction 仍是规则优先的半自动候选抽取

v9 extraction 只应生成 candidate，不应直接生成生效需求。这一点必须保留。任何 LLM 抽取都只能进入候选池，不能绕过 review / promote。

### 4.5 GitHub 写权限未实际可用

仓库 metadata 曾显示 push/admin 权限，但 create branch / create tree 返回 403。因此当前交付仍是 zip 补丁包，本审计包也按本地应用方式设计。

## 5. 建议落地顺序

不要直接一次性 merge 到 main。建议顺序：

```text
1. 本地新建 feature 分支。
2. 解压完整包。
3. 运行 CLI / answer / API integration 脚本。
4. 运行 audit 脚本。
5. 运行 unittest。
6. 运行 smoke orchestrator。
7. 检查 report。
8. 人工查看 diff。
9. 开 PR。
10. PR 只合入代码和文档，不合入 runtime 数据库。
```

## 6. 一键审计命令

```bash
python scripts/audit_requirement_program.py --repo-root .
```

如需同时跑单元测试：

```bash
python scripts/audit_requirement_program.py --repo-root . --run-tests
```

报告输出：

```text
.requirement_program_runtime/reports/requirement_program_audit.json
.requirement_program_runtime/reports/requirement_program_audit.md
```

## 7. 推荐验收命令

```bash
python scripts/audit_requirement_program.py --repo-root . --run-tests

python scripts/run_requirement_program.py \
  --root .requirement_program_runtime/knowledge_base \
  --mode smoke
```

如果这两个命令都通过，才进入 PR review。

## 8. 当前审计结论

以补丁包自包含结构看，系统已经具备工程闭环：需求导入、解析、合规、影响、审批、基线、门禁、ECO、自动验证都已覆盖。

但正式进入长期维护前，建议重点处理三件事：

1. 把 schema 迁移到正式 migration 体系。
2. 给 ECO / baseline / approval 增加显式 transaction 边界。
3. 根据真实 `api_server` 结构选择唯一 API 接入方式。

这三项不影响 MVP 验证，但影响长期维护质量。

## 9. 关于独立解压包与真实仓库验证

本 zip 是 overlay 包，不是完整仓库快照。它不包含 EVT 仓库已有的基础文件，例如：

```text
pyproject.toml
src/enterprise_agent_kb/config.py
src/enterprise_agent_kb/db.py
src/enterprise_agent_kb/cli.py
```

因此不要在单独解压目录中直接把 `python -m unittest discover` 当作最终结论。正确方式是在真实 EVT 仓库根目录中解压并应用集成脚本后运行：

```bash
python scripts/audit_requirement_program.py --repo-root . --run-tests
python scripts/run_requirement_program.py --root .requirement_program_runtime/knowledge_base --mode smoke
```

审计脚本已经加入 `base.repository.files` 检查；如果没有在真实仓库根目录运行，会直接失败并提示缺失基础文件。

## Phase 3: 事务模型硬化（2026-07-13）

Phase 3 修复了 Requirement Resolver 的系统性事务边界缺陷。所有改动均为内部事务收敛，不改变对外 API 契约。

### 根因缺陷（7 项）

1. ECO `apply_change`：variant 更新+事件+ECO 状态在一个 connection 提交，但 effective 刷新在独立的 per-project connection 中执行。若刷新失败，variant 已变更且 ECO 状态已 'applied'，但 effective 需求是 stale 的。
2. ECO `close_with_release_gate`：调用 baseline freeze（独立 connection+commit）、gate evaluate（独立 connection+commit）、再更新 ECO 状态。任一中途失败，baseline 已冻结但 ECO 状态未更新。
3. ECO `submit_for_approval`：先创建 approval（独立 connection+commit），再更新 ECO 状态到 'approval_pending'。第二步失败则 approval 已存在但 ECO 状态 stale。
4. ECO 无并发保护：两个并发 `apply_change` 可同时修改同一 requirement_variant，无锁、无版本检查。
5. Approval 无正式状态机：状态转换无校验（'rejected' -> 'approved' 未被阻止）；事件用 INSERT OR REPLACE 导致重复 event_id 静默覆盖。
6. Baseline `_next_version` 用 COUNT(*)+1 生成版本号，并发 freeze 可产生相同 baseline_version。
7. Baseline compliance 异常未与 freeze 操作隔离。

### 修复方案

**Repository 层（repository.py）**：新增 `_TxnConnectionProxy` 代理类，`transaction()` 上下文管理器绑定单一 connection，`connection()`/`_conn_ctx()` 在事务激活时返回代理。代理的 `commit()`/`close()` 为 no-op，`rollback()` 透传，其他方法通过 `__getattr__` 透传到真实 connection。59 个 `closing(self.connection())` / `closing(self.repo.connection())` 调用替换为 `self._conn_ctx()` / `self.repo._conn_ctx()`。

**Approval 状态机（approval.py）**：`approve()`/`reject()` 预检查 `current_status != 'submitted'` 则 raise；原子 `UPDATE ... WHERE approval_status='submitted'`，`cursor.rowcount==0` 则 rollback 并 raise "state changed concurrently"。Override 更新条件为 `approval_status='draft'`（override 初始为 draft）。

**Baseline 事务（baseline.py）**：移除显式 `BEGIN IMMEDIATE`（proxy 模式下会冲突；Python sqlite3 自动 deferred BEGIN；proxy 保证 ECO 内单 connection 无并发竞争）；版本在持有 connection 内计算；重复 baseline_id raise 并回滚；compliance 失败回滚整个 freeze。

**ECO 单事务边界（eco.py）**：`submit_for_approval`/`approve`/`apply_change`/`close_with_release_gate` 四个跨服务方法用 `self.repo.transaction()` 包裹。子服务（approval/baseline/gate/resolver）通过共享 repo 自动复用 proxy connection，内部 `commit()` 变 no-op，仅外层 ECO owner 提交。任一子步骤失败则整个操作回滚。

### 验证

- 95 个 requirement 测试通过（92 既有 + 3 新事务边界测试）
- 3 个 ECO 事务边界测试验证关键回滚场景：impact 分析失败回滚 variant+ECO status；gate 评估失败回滚 baseline；approval 创建失败不前进 ECO status
- KB1 主线回归无影响（cli_submodules 22/22、closed_loop_schema 21/21、answer_safety 9/9）
