# Requirement Program 事务与异常策略

## 1. 原则

Requirement Program 的核心数据具有工程治理属性，不能按普通缓存处理。

必须区分：

```text
事实源：RequirementVariant / Override / Approval / TestResult / Baseline / ECO
派生状态：EffectiveRequirement / ReleaseGateRun / ImpactReport / ComplianceMatrix
```

派生状态可以重建，事实源必须有审计事件。

## 2. 事务边界建议

### 2.1 单步写入

可以由 repository method 独立提交：

```text
create customer
create project
create profile
insert candidate
insert test result
```

### 2.2 业务闭环写入

必须使用 service-level transaction：

```text
promote candidate
approve override
freeze baseline
apply ECO
close ECO
release gate evaluation persistence
```

原因：这些操作会跨表写入，任何中间失败都不能留下半完成状态。

## 3. ECO 推荐事务

`apply_eco` 应是一个事务：

```text
BEGIN
  update source requirement variant
  insert eco event
  refresh effective requirements
  freeze new baseline if requested
COMMIT
```

如果任一步失败：

```text
ROLLBACK
  ECO remains approved / apply_failed
  write error event
```

## 4. Approval 推荐事务

`approve_approval` 应是一个事务：

```text
BEGIN
  update requirement_approvals.status
  insert requirement_approval_events
  update requirement_overrides.approval_status if target is override
COMMIT
```

## 5. Baseline 推荐事务

`freeze_baseline` 应是一个事务：

```text
BEGIN
  resolve current effective requirements
  insert requirement_baselines
  insert requirement_baseline_items
  insert baseline event
COMMIT
```

## 6. 错误状态建议

建议所有长流程都使用显式状态：

```text
draft
submitted
approved
rejected
applying
apply_failed
applied
closed
gate_blocked
cancelled
```

不要只靠异常栈判断业务状态。

## 7. 日志与审计

工程治理流程至少记录：

```text
actor
action
target_type
target_id
previous_status
new_status
reason
created_at
payload_json
```

## 8. 幂等性

以下操作应尽量幂等：

```text
init-schema
seed-sample
apply integration scripts
freeze baseline with same name + same content
release gate evaluation read path
list commands
```

以下操作不应静默幂等，应返回已有对象或拒绝重复执行：

```text
approve same approval twice
apply same ECO twice
promote same candidate twice
close already closed ECO
```
