# Requirement Program 合并准备清单

## 1. 本地准备

```bash
git checkout -b feature/requirement-program-integrated
unzip evt_requirement_resolver_integrated_program_system_audit.zip
```

## 2. 应用集成脚本

```bash
python scripts/apply_requirement_cli_integration.py
python scripts/apply_requirement_answer_api_integration.py
```

API 接入可选：

```bash
python scripts/apply_requirement_api_integration.py
```

## 3. 审计

```bash
python scripts/audit_requirement_program.py --repo-root . --run-tests
```

## 4. Smoke 验证

```bash
python scripts/run_requirement_program.py \
  --root .requirement_program_runtime/knowledge_base \
  --mode smoke
```

## 5. 必须检查的 diff

```bash
git diff --stat
git diff src/enterprise_agent_kb/cli.py
git diff src/enterprise_agent_kb/answer_api.py
git diff src/enterprise_agent_kb/api_server.py
```

重点看：

1. `cli.py` 是否只增加 requirement 子命令入口。
2. `answer_api.py` 是否只在入口前增加默认关闭的 soft-router。
3. `api_server.py` 是否只增加 requirement router include；如果自动脚本拒绝修改，手工评估。
4. `requirements/` 子包是否没有污染现有主链。
5. `tests/` 是否只新增 requirement 测试。

## 6. 不应提交的内容

不要提交：

```text
.requirement_program_runtime/
knowledge_base/db/knowledge.db
__pycache__/
*.pyc
临时测试输出
本地客户真实需求文档
```

## 7. PR 描述模板

```markdown
## Summary

Adds integrated Requirement Program for customer/project-specific OBC/DCDC requirements:

- Requirement resolver
- Customer/project profiles and overlays
- Compliance matrix
- Impact analysis
- Approval governance
- Candidate extraction and package import
- Project baseline versioning
- Release readiness gate
- ECO workflow
- CLI, optional answer soft-router, optional API adapter
- Audit and smoke orchestrator

## Safety

- Existing answer flow is not changed unless `EAKB_ENABLE_REQUIREMENT_ROUTER=1`.
- API integration script refuses unsafe automatic insertion.
- Requirement extraction creates candidates only; it does not directly promote facts.

## Validation

- [ ] `python scripts/audit_requirement_program.py --repo-root . --run-tests`
- [ ] `python scripts/run_requirement_program.py --root .requirement_program_runtime/knowledge_base --mode smoke`

## Notes

Schema is currently provided as requirement subsystem schema SQL. Follow-up should move it to formal migrations.
```
