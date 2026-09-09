# KB1 Ontology System Roadmap

**Status**: Approved (grill session 2026-06-08)
**Approach**: Parallel system, fully isolated, test-driven, phased delivery

## High-Level Structure

```
src/enterprise_agent_kb/   ← 现有系统（不碰）
src/kb1_ontology/          ← 新本体系统（独立）
    ├── class_registry/    ← 类注册与管理
    ├── entity_manager/    ← 实体管理
    ├── relation_registry/ ← 关系注册与管理
    ├── attribute_store/   ← 属性存储
    ├── storage/           ← 独立 DB (ontology.db)
    ├── cli/               ← CLI 入口
    └── tests/             ← 单元 + 集成测试

docs/ontology/             ← 设计与测试报告
    ├── CONTEXT.md         ← 本体论词汇表
    ├── ROADMAP.md         ← 本文件
    ├── adr/               ← 架构决策记录
    └── test_reports/      ← 每阶段测试报告
```

## Phased Delivery

每个阶段都遵循"定义准入准则 → 实现 → 写测试 → 跑测试 → 写报告"的循环。

---

### **Phase 0: 项目脚手架**

**目标**：建立独立的项目结构，不写业务代码。

**范围**：
- `src/kb1_ontology/` 目录结构
- `pyproject.toml` 或 `setup.py` 独立可安装
- 独立 SQLite DB（`ontology.db`）
- 空 `__init__.py` 文件
- 测试基础设施（pytest, fixtures）

**准入准则**（开始前确认）：
- [ ] 现有 KB1 系统未受影响
- [ ] 新模块能 import
- [ ] 测试能运行（即使无测试）

**测试计划**：
- 单元测试：`test_scaffolding.py` — 验证模块能 import，DB 能连接
- 集成测试：`test_smoke.py` — 验证 CLI 能启动

**完成标准**：
- 现有 KB1 的所有测试仍通过
- 新模块的 5 个 smoke test 通过
- 测试报告：`docs/ontology/test_reports/PHASE_0_SCAFFOLDING.md`

---

### **Phase 1: 类注册表 (Class Registry)**

**目标**：实现 `class_def` 表 + CRUD + 3 层层次 + 核心类种子。

**范围**：
- `class_registry/` 模块
- 表 `class_def` (class_id, class_name, parent_class_id, layer, domain, ...)
- CRUD API: `create_class`, `get_class`, `list_classes`, `update_class`, `delete_class`
- 层次查询: `get_ancestors`, `get_descendants`, `is_subclass_of`
- **核心类种子**：手动定义 Meta 层 + Systems Engineering Domain 的初始类

**核心类种子（Systems Engineering Domain，OBC 焦点）**：
```
Meta:
- Thing
  - InformationEntity
  - PhysicalEntity
  - ProcessEntity
  - ConceptEntity
  - RoleEntity

OBC Domain (Systems Engineering):
- InformationEntity.Standard
- InformationEntity.Specification
- InformationEntity.Guideline
- PhysicalEntity.Device
- PhysicalEntity.Component
- ProcessEntity.ChargingProcess
- ProcessEntity.DiagnosticProcess
- ConceptEntity.Parameter
- ConceptEntity.Constraint
- ConceptEntity.Protocol
```

**Note on Domain naming**: The Domain identifier is "OBC" for now
because the OBC system is the prototype. The class hierarchy
is shared across all Systems Engineering work — the label refers
to the systems engineer's scope. Future Software / Electronics /
Test domains can coexist under Meta without disturbing OBC.

**准入准则**：
- [ ] 18+ 个核心类已种子
- [ ] 3 层层次验证通过
- [ ] is-a 关系查询正确

**测试计划**：
- 单元测试：每个 CRUD 函数
- 层次测试：is_subclass_of, get_ancestors
- 集成测试：从根 Thing 遍历整棵树
- 一致性测试：无循环依赖、parent 必须存在

**完成标准**：
- 100% CRUD API 单元测试通过
- 层次查询 100% 正确
- 无循环依赖
- 测试覆盖率 ≥ 90%
- 测试报告：`docs/ontology/test_reports/PHASE_1_CLASS_REGISTRY.md`

---

### **Phase 2: 实体管理器 (Entity Manager)**

**目标**：实现 `entity` 表 + CRUD + class 归属 + 别名合并 + 规范化去重。

**范围**：
- `entity_manager/` 模块
- 表 `entity` (entity_id, canonical_name, class_id, domain, aliases_json, ...)
- **Document 关联 job_role**: 文档入库时记录 `document.job_roles` 列表
  （e.g., `["systems_engineer", "software_engineer"]`）
- CRUD API: `create_entity`, `get_entity`, `find_or_create`, `merge_aliases`
- 规范化：`normalize_canonical_name` (移除年份、统一连字符)
- 去重逻辑：基于 (canonical_name, class_id, domain)
- 别名合并：相同 canonical 的不同写法合并

**准入准则**：
- [ ] 实体 CRUD 工作
- [ ] 规范化函数有效（"ISO 14229-1—2013" → "ISO 14229-1"）
- [ ] 去重逻辑正确（同名同 class 不会重复创建）
- [ ] 别名合并正确
- [ ] document.job_roles 字段可读可写

**测试计划**：
- 单元测试：CRUD, normalize, merge, job_role
- 去重测试：相同规范化名应该只创建一次
- 集成测试：用 30 个真实标准代码测试去重
- Job role 测试：文档可关联多岗位

**完成标准**：
- 30+ 真实标准代码测试通过
- "ISO 14229-1" 和 "ISO 14229-1—2013" 被识别为同一实体
- 文档可正确关联多个 job_role
- 测试报告：`docs/ontology/test_reports/PHASE_2_ENTITY_MANAGER.md`

---

### **Phase 3: 关系注册表 (Relation Registry)**

**目标**：实现 `relation_def` 表 + `relation` 实例表。

**范围**：
- `relation_registry/` 模块
- 表 `relation_def` (relation_id, relation_name, category, scope, ...)
- 表 `relation` (relation_instance_id, relation_id, src, dst, ...)
- 4 类核心关系种子（structural, attributive, referential, temporal）
- 关系查询：`get_relations_of`, `get_related_entities`

**核心关系种子**：
```
Structural:   is-a, part-of
Attributive:  has-attribute
Referential:  references, cites
Temporal:     precedes, follows
```

**准入准则**：
- [ ] 关系定义 CRUD
- [ ] 关系实例 CRUD
- [ ] 4 类关系已种子
- [ ] 关系查询正确

**测试计划**：
- 单元测试：CRUD
- 关系图遍历测试：从一个 entity 出发，遍历 N 跳
- 类别验证：每个关系都属于 4 类之一
- 作用域验证：core 关系可被任何 domain 使用

**完成标准**：
- 5+ 核心关系种子通过
- 关系图遍历测试 100% 正确
- 测试报告：`docs/ontology/test_reports/PHASE_3_RELATION_REGISTRY.md`

---

### **Phase 4: 属性存储 (Attribute Store)**

**目标**：实现 `attribute` 表（三元组形式）。

**范围**：
- `attribute_store/` 模块
- 表 `attribute` (subject, attr_name, value_*, value_type, ...)
- API: `set_attribute`, `get_attribute`, `query_attribute`
- 4 种值类型支持：string, number, range, reference

**准入准则**：
- [ ] 4 种值类型都能存取
- [ ] 范围值能正确解析（"50 ± 10 ms" → {min, max, unit}）
- [ ] 引用值能正确解析（指向另一个 entity_id）

**测试计划**：
- 单元测试：每种值类型
- 范围解析测试：各种格式的字符串
- 引用测试：值是 entity_id 时能正确反查
- 集成测试：基于属性的查询（如"P2 定时参数的所有值"）

**完成标准**：
- 4 种值类型 100% 测试覆盖
- 范围解析 10+ 真实数据测试通过
- 测试报告：`docs/ontology/test_reports/PHASE_4_ATTRIBUTE_STORE.md`

---

### **Phase 5: 端到端查询演示**

**目标**：用 OBC Domain 真实数据演示"本体驱动查询"。

**范围**：
- 选择 OBC Domain 的 3-5 个真实标准（如 ISO 14229 系列、GB/T 18487）
- 手工建本体（不依赖自动抽取）
- 演示查询："OBC 充电协议的所有参数"
- 对比 RAG 风格 vs 本体驱动风格

**准入准则**：
- [ ] 5+ 真实标准已建本体
- [ ] 至少 3 个示例查询
- [ ] 演示对"RAG 难回答"的查询有效

**完成标准**：
- 演示报告：`docs/ontology/test_reports/PHASE_5_DEMO.md`
- 包含对比：传统 RAG vs 本体驱动

---

### **Phase 7 (Future): 半自动本体维护工具**

**目标**：当新文档入库时，自动提取候选本体条目（实体、关系、属性），
由领域专家审核后一键入库。

**范围**：
- **候选实体提取**：正则匹配标准号（ISO \d+-\d+, GB/T \d+\.\d+ 等）
- **候选属性提取**：识别"额定电压 250 V"、"P2 timing 50 ms"等模式
- **候选关系提取**：识别"引用"、"参见"、"depends on"等文本模式
- **人工审核界面**：专家查看候选列表，勾选确认后批量入库

**不在 MVP 范围内**。当前手动构建的 13 实体 + 13 关系 + 27 属性
已足够支撑结构化查询演示。Phase 7 的价值在于"增量维护"：
当知识库从 13 个标准扩展到 100+ 时，手动维护成本过高，
半自动工具可以大幅降低工作量。

**设计原则**：
- 自动提取是"建议"，不是"决策"——专家始终有否决权
- 提取准确率不需要 100%，只需要"足够好"让专家审核效率提升 10x
- 优先支持"标准文档"（格式最规范），再扩展到"技术规范"和"论文"

**准入准则**：
- [ ] 自动提取的标准号准确率 ≥ 90%
- [ ] 自动提取的参数值（数字+单位）准确率 ≥ 80%
- [ ] 专家审核界面可用（CLI 或 Web）
- [ ] 审核后的入库操作原子化（全部成功或全部回滚）

---

## Test Coverage Targets

**Principle**: Tests serve the **goal of each phase**, not
"re-run the existing test suite". Tests are designed bottom-up
from the phase's acceptance criteria.

| Phase | 目标覆盖率 | 准入测试数 | 完成标准 |
|-------|-----------|----------|---------|
| Phase 0 | 100% smoke | 6 | 现有系统零影响 |
| Phase 1 | ≥ 90% | 32+ | 16+ 类种子, 3 层验证 |
| Phase 2 | ≥ 90% | 34+ | 30+ 真实标准去重通过 |
| Phase 3 | ≥ 90% | 28+ | 4 类关系, 遍历正确 |
| Phase 4 | ≥ 90% | 26+ | 4 种值类型, 范围解析, reference 类型 |
| Phase 5 | n/a | 5+ | 演示报告 |
| Phase 6 | ≥ 90% | 70+ | 55+ E2E, 14 组合查询, use_legacy 参数 |

## Test Design Principle (revised)

**Tests must be designed from each phase's goals, not copied from
the existing system.**

For each phase, before writing code, the test plan answers:
1. **What is this phase trying to achieve?** (the goal)
2. **What would prove it works?** (acceptance criteria)
3. **What tests will demonstrate each criterion?** (test design)
4. **What data do the tests need?** (fixtures, examples)

The existing KB1 test suite is **not** the reference. It tests
the existing implementation. The new system has different goals
(ontology-driven queries) and needs its own test suite designed
specifically for those goals.

When we evaluate the new system against the old one (Phase 5
onward), we do so using **golden questions** that test the
shared goal: answering the user's question correctly. This is
different from "make the new tests pass the old assertions."
