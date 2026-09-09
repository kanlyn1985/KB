# Agentic Knowledge Base — Local AI + GitHub V-Model Development Workflow

- Document ID: AKB-DEV-001
- Version: V1.0
- Status: Engineering Working Agreement
- Branch: `rebuild/agent-kb-core`

## 1. Operating Model

本项目采用：

> **设计由架构负责人主导，本地 AI 负责代码与测试执行，GitHub 负责任务、代码、结果和审计中转。**

角色边界：

| 角色 | 责任 |
|---|---|
| Architecture/Design | 需求、架构、数据模型、接口、验收标准、技术决策、评审 |
| Local AI | 按 GitHub 任务实现代码、运行测试、生成证据和报告，不自行改变需求基线 |
| GitHub | 唯一中转载体：requirements/design/tasks/code/test-results/reports |
| Human Reviewer | 对架构基线、关键设计和发布 Gate 做批准 |

## 2. Single Source of Coordination

GitHub 当前开发分支：`rebuild/agent-kb-core`。

所有正式设计、任务、代码变更、测试结果必须能够回到 GitHub 中的明确提交或文档。

本地 AI 不应以聊天记录作为唯一任务来源；任务必须落成 GitHub 文档、任务清单或受控变更。

## 3. V-Model Increment Loop

每个增量严格执行：

```text
Requirement
  -> Design
  -> Task
  -> Implementation
  -> Unit/Contract Test
  -> Integration Test
  -> Evidence Report
  -> Review
  -> Accept / Reject
```

禁止“先写代码再补需求”。

## 4. Local AI Execution Contract

本地 AI 每次执行必须：

1. 阅读对应 SRS/Data Model/ICD 文档。
2. 只实现任务范围内的修改。
3. 不擅自修改需求、Canonical Model 或接口语义。
4. 运行任务要求的测试和回归测试。
5. 保存测试命令、环境、结果、失败信息和相关 artifact。
6. 将变更提交到 GitHub，并提供 commit SHA。
7. 对失败如实报告，不用“测试通过”替代未执行的测试。

## 5. Architecture Owner Review Contract

设计侧每次评审至少检查：

- 是否满足需求 ID；
- 是否违反 System Invariants；
- 是否破坏 Canonical Data Model；
- 是否破坏 ICD；
- 是否引入重复基础设施；
- 是否有足够测试覆盖；
- 是否需要更新 RTM/ADR。

## 6. GitHub as Handoff Protocol

推荐最小工作流：

```text
Design Note / Task Spec
        ↓
GitHub commit
        ↓
Local AI pulls latest branch
        ↓
Implementation
        ↓
Tests
        ↓
Commit + test evidence
        ↓
Architecture review
        ↓
Next task
```

## 7. Change Classification

| 类型 | 处理 |
|---|---|
| P0/P1 需求修改 | 必须变更 SRS + RTM，并记录 CR/ADR |
| Canonical Model 修改 | 必须更新 Data Model + ICD + Tests |
| Interface 修改 | 必须更新 ICD + Consumer tests |
| 实现重构 | 不得改变外部契约；需要回归测试 |
| Bug Fix | 需要新增/修改回归测试 |
| 性能调优 | 必须提供 benchmark 对比 |

## 8. Evidence Required for Done

每个开发增量至少留下：

```text
commit SHA
changed files
commands executed
test summary
known limitations
requirement IDs
verification IDs
```

## 9. Release Gate

未通过对应 V&V Gate 的代码不得作为该增量的完成版本。

```text
Design Gate
  ↓
Implementation Gate
  ↓
Verification Gate
  ↓
Review Gate
  ↓
Release Gate
```

## 10. Current Sequence

```text
SRS V1.1
  ↓
Data Model V1.0
  ↓
ICD V1.0
  ↓
V&V Plan V1.0
  ↓
RTM V1.0
  ↓
Golden Knowledge Dataset V1.0
  ↓
ADR + Architecture Review
  ↓
V0.1 Evidence Core
```
