# KB1 全量开发实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成 KB1 的四个产品闭环（入库、召回、答案、回归），达到全库检索质量和答案质量可评估、可追溯、可持续改进的状态。

**Architecture:** 保留现有 55 模块骨架，按四个优先级分批增强。P1 补全全库 retrieval_quality 黄金集并建立基线；P2 拆出 parameter_value 策略扩充答案质量；P3 引入过程/时序一等对象；P4 用 KB 数据自动构建歧义索引。

**Tech Stack:** Python 3.14, SQLite, httpx, PyMuPDF, MiniMax LLM API

---

## 当前数据库状态

| 表 | 行数 | 说明 |
|---|---:|---|
| documents | 6 | DB 中 6 个文档，JSON facts 中有 13 个 |
| pages | 617 | |
| blocks | 657 | |
| evidence | 608 | |
| facts | 3,863 | |
| entities | 844 | |
| wiki_pages | 1,245 | |
| graph_edges | 1,332 | |
| source_units | 2,250 | |
| golden_cases | 883 | |
| retrieval_runs | 576 | |
| eval_runs | 25 | |
| eval_results | 156 | |
| repair_tasks | 3 | |

已有 golden.json 的文档: DOC-000003, DOC-000004, DOC-000005, DOC-000009, DOC-000012, DOC-000013
有 facts.json 但无 golden.json 的文档: DOC-000001, DOC-000002, DOC-000006, DOC-000007, DOC-000008, DOC-000010, DOC-000011

---

## Priority 1: 全库 retrieval_quality 黄金集

### Task 1.1: 分析现有 golden cases 的 assert_mode 分布

**Files:**
- Read: `tests/generated/*.golden.json`
- Read: `knowledge_base/db/knowledge.db` golden_cases 表

**Step 1:** 编写分析脚本，统计每个文档的 golden cases 按 assert_mode 分布

运行 SQL:
```sql
SELECT doc_id, assert_mode, COUNT(*) as cnt
FROM golden_cases
WHERE status = 'active'
GROUP BY doc_id, assert_mode
ORDER BY doc_id, assert_mode;
```

**Step 2:** 确认哪些文档缺少 retrieval_quality 类型用例

**Step 3:** 输出分布报告，确定补生成策略

### Task 1.2: 为缺失 golden 的文档生成 golden tests

**Files:**
- Modify: `src/enterprise_agent_kb/generated_tests.py`（如果需要调整生成逻辑）
- Create: `tests/generated/{DOC-ID}.golden.json`（由 generate 函数自动创建）

**Step 1:** 检查 DOC-000001/002/006/007/008/010/011 是否在 documents 表中

如果不在 DB 中，需要先注册入库。如果只有 JSON 文件没有 DB 记录，需要补注册。

**Step 2:** 对每个缺失文档运行 golden 生成:
```
POST /generate-golden-tests {"doc_id": "DOC-000001"}
```
或通过 CLI:
```
eakb --root knowledge_base generate-golden-tests --doc-id DOC-000001
```

**Step 3:** 确认生成结果包含 retrieval_quality 类型用例

### Task 1.3: 确保现有 golden 用例中 retrieval_quality 占比合理

**Files:**
- Modify: `src/enterprise_agent_kb/generated_tests.py` — `_build_local_cases()` 和 `_build_network_cases()`

**Step 1:** 检查 `_build_network_cases` 是否生成 `retrieval_quality` 类型用例（有 `retrieval_must_hit`、`expected_pages`、`expected_sections`、`negative_expected` 字段的用例）

**Step 2:** 如果 `_build_local_cases` 只生成 `context_contains` 类型，增加 `retrieval_quality` 生成路径：
- 从 source_units 的高 importance 单元生成用户式查询
- 标注 must_hit（至少 1 个）、expected_pages、expected_sections
- 为标准/规范文档按设计文档中的比例配方生成

**Step 3:** 补充 retrieval_quality 用例生成函数:

```python
def _build_retrieval_quality_cases(
    local_context: dict[str, object],
    target_count: int,
) -> list[dict[str, object]]:
    """Generate retrieval_quality cases with must_hit, expected_pages, negative_expected."""
    ...
```

**Step 4:** 在 `generate_golden_tests_for_document` 中调用并合并

### Task 1.4: 运行全库 golden 并建立 Recall@K 基线

**Files:**
- Create: `docs/plans/retrieval_quality_baseline.md`（报告文件）

**Step 1:** 对每个有 golden 的文档运行 golden tests:
```
POST /run-golden-tests {"doc_id": "DOC-000003"}
```

**Step 2:** 收集所有 eval_runs 的 result_summary_json 中的 retrieval_quality 数据

**Step 3:** 输出全库基线报告:
```text
DOC-000001: Recall@5=?, Recall@10=?, MRR=?
DOC-000002: Recall@5=?, Recall@10=?, MRR=?
...
全库平均: Recall@5=?, Recall@10=?, MRR=?
```

**Step 4:** 识别 Recall@5 < 85% 的文档，作为后续优化目标

### Task 1.5: 全库 coverage report 更新

**Files:**
- Create: `knowledge_base/coverage_reports/all_docs_*.json`

**Step 1:** 对所有入库文档重新 build coverage:
```
POST /build-document-and-test {"doc_id": "DOC-000001"}
```
或通过 CLI 批量执行

**Step 2:** 生成全库 uncovered priority report

**Step 3:** 验证 source_units 表数据完整

---

## Priority 2: answer_quality 扩充

### Task 2.1: 新增 parameter_value 策略

**Files:**
- Modify: `src/enterprise_agent_kb/answer_policy.py` — `select_answer_policy()`, `build_direct_answer()`
- Modify: `src/enterprise_agent_kb/query_rewrite.py` — 增加 `parameter_value` query_type 识别
- Test: `tests/test_answer_policy.py`

**Step 1:** 编写测试:
```python
def test_parameter_value_query_returns_value():
    policy = select_answer_policy("parameter_lookup", "CC阻值是多少")
    # 应返回 "parameter_value" 或 "parameter_lookup" 可以走 parameter_value 路径
```

**Step 2:** 在 `select_answer_policy` 中新增 `parameter_value` 识别:
- 查询包含"是多少"、"是多少V"、"数值"、"等于"等值信号词
- 同时有参数锚点（阻值/电压/电流/占空比/频率/检测点）
- 且不是释义型问法（排除"是什么意思"/"代表什么"）

**Step 3:** 在 `build_direct_answer` 中新增 `parameter_value` 策略:
- 从 parameter_value 类型 facts 中提取标称值/最大值/最小值/单位
- 输出格式: "CC阻值的标称值为 X Ω，范围 max Y / min Z。依据来自表 A.1。"

**Step 4:** 运行测试确认

### Task 2.2: 补充 answer_quality golden cases

**Files:**
- Modify: `src/enterprise_agent_kb/generated_tests.py` — `_build_local_cases` 或新增 `_build_answer_quality_cases`

**Step 1:** 定义 answer_quality 用例模板:
```json
{
  "query": "CC阻值是多少",
  "must_include": ["CC阻值", "Ω"],
  "assert_mode": "rich_answer",
  "expected_answer_mode": "parameter_value",
  "forbidden_contains": ["没有找到", "GB：代替"],
  "expected_evidence_shape": "parameter_value"
}
```

**Step 2:** 从高价值参数对象自动生成 answer_quality 用例:
- 遍历 parameter_topic entities
- 为每个生成"释义"、"值查询"、"信号状态"三种问法
- 标注 expected_answer_mode 和 forbidden_contains

**Step 3:** 合并进 golden suite

### Task 2.3: forbidden_contains 检查增强

**Files:**
- Modify: `src/enterprise_agent_kb/answer_quality.py` — `_forbidden_hits()`
- Test: `tests/test_answer_quality.py`

**Step 1:** 确认 `forbidden_contains` 字段是否已被 golden case 使用

**Step 2:** 如果 `_forbidden_hits` 只检查 case 级 `forbidden_contains`，确保它也从 case metadata 中读取

**Step 3:** 新增默认 forbidden 规则（对所有 case 都适用）:
- "没有找到足够的结构化结果" (no_answer_candidate 的标准回复)
- "GB：代替" (替换噪声)
- 无意义截断

**Step 4:** 运行 golden 测试验证

---

## Priority 3: Phase 2 过程/时序模型

### Task 3.1: 定义 process_fact / transition_fact schema

**Files:**
- Modify: `src/enterprise_agent_kb/facts.py` — 新增 process/transition fact 抽取
- Modify: `src/enterprise_agent_kb/entities.py` — 新增 process/state/transition entity 类型

**Step 1:** 定义 fact payload:
```python
process_fact_payload = {
    "process_name": "交流充电控制时序",
    "table_title": "表 A.7",
    "states": [...],
    "transitions": [...],
    "timing_constraints": [...],
}
transition_fact_payload = {
    "from_state": "状态 2",
    "to_state": "状态 3",
    "trigger": "检测点 1 电压从 6V 变为 9V",
    "timing_max": "5s",
    "action": "供电设备闭合 S2",
}
```

**Step 2:** 在 entities 中新增 entity_type:
- `process` — 过程
- `state` — 状态
- `transition` — 状态迁移

### Task 3.2: 从时序表抽取 process/transition facts

**Files:**
- Modify: `src/enterprise_agent_kb/facts.py` — `_extract_process_facts()`, `_extract_transition_facts()`
- Test: `tests/test_facts.py`

**Step 1:** 识别时序类知识单元（已有 `procedure` 类型单元）

**Step 2:** 对表格型 procedure（表头含"状态"、"时序"、"动作"、"时间"）:
- 每行生成一个 transition_fact
- 整表生成一个 process_fact
- 建立关联 graph edges

**Step 3:** 对文字型 procedure:
- 按"步骤/阶段/状态"分句
- 生成 process_fact

### Task 3.3: 建立时序查询路由

**Files:**
- Modify: `src/enterprise_agent_kb/query_rewrite.py` — 确保 `timing_lookup` 路由正确
- Modify: `src/enterprise_agent_kb/topic_resolution.py` — process/state entity 匹配
- Modify: `src/enterprise_agent_kb/answer_policy.py` — `_build_process_answer()` 增强
- Test: `tests/test_query_rewrite.py`

**Step 1:** 确认 `timing_lookup` 已覆盖时序类问法:
- "CP的时序是什么样的" → timing_lookup (已有)
- "交流充电控制时序" → timing_lookup
- "状态 2 到状态 3" → timing_lookup
- "握手流程" → timing_lookup

**Step 2:** topic resolution 对 timing_lookup 优先匹配 process entity

**Step 3:** `_build_process_answer` 增强:
- 有 transition_facts 时输出状态迁移链
- 有 timing_constraints 时输出时间约束

### Task 3.4: 时序回归测试集

**Files:**
- Create: `tests/test_timing_regression.py`

**Step 1:** 定义时序回归用例:
```python
TIMING_REGRESSION_CASES = [
    {"query": "CP的时序是什么样的", "must_include": "表 A.7", "expected_query_type": "timing_lookup"},
    {"query": "交流充电控制时序", "must_include": "表 A.7"},
    {"query": "直流充电紧急停机时序", "must_include": "紧急停机"},
    {"query": "状态 2 到状态 3 的触发条件", "must_include": "检测点"},
    ...
]
```

**Step 2:** 运行回归确认通过率

---

## Priority 4: KB-driven 歧义索引

### Task 4.1: 从 KB 数据发现 acronym senses

**Files:**
- Create: `src/enterprise_agent_kb/ambiguity_index.py`
- Test: `tests/test_ambiguity_index.py`

**Step 1:** 编写 `build_ambiguity_index()`:
```python
def build_ambiguity_index(connection) -> dict[str, list[Sense]]:
    """从 entities/facts/wiki/graph 自动发现缩写含义。"""
    # 1. 从 entities.alias_json 提取缩写
    # 2. 从 facts 中 term_definition 提取 "缩写 全称" 模式
    # 3. 从 wiki_pages.title 提取 "全称 (缩写)" 模式
    # 4. 对同一缩写聚合所有 sense
    # 5. 每个 sense 标注 context_terms
```

**Step 2:** Sense 数据结构:
```python
@dataclass
class Sense:
    label: str              # "控制导引功能 / control pilot"
    entity_id: str          # "ENT-053454"
    fact_ids: list[str]     # ["FACT-053454"]
    context_terms: list[str] # ["控制导引", "充电接口"]
    example_query: str      # "充电接口里的 CP 控制导引功能是什么意思"
    confidence: float
```

### Task 4.2: 替换人工 ambiguity registry

**Files:**
- Modify: `src/enterprise_agent_kb/query_ambiguity.py` — 从 KB index 读取
- Test: `tests/test_query_ambiguity.py`

**Step 1:** 在 `detect_query_ambiguity` 中:
- 先查 KB-built ambiguity index
- 如果缩写有多个 sense 且无上下文，返回 clarification
- 如果只有 1 个 sense，直接返回该 sense（不需要澄清）
- 人工 registry 作为高风险种子兜底

**Step 2:** 缓存策略:
- 入库时构建 index，存入 DB 或 JSON
- 查询时直接读缓存

### Task 4.3: 歧义索引持久化和更新

**Files:**
- Modify: `src/enterprise_agent_kb/pipeline.py` — 在 pipeline 中增加 build_ambiguity_index 步骤
- Create: `knowledge_base/ambiguity_index.json`（输出文件）

**Step 1:** 在 pipeline 的 wiki/graph 步骤后调用 `build_ambiguity_index()`

**Step 2:** 输出到 `knowledge_base/ambiguity_index.json`

**Step 3:** 查询时从文件加载，fallback 到人工 registry

### Task 4.4: 歧义索引回归测试

**Files:**
- Test: `tests/test_ambiguity_index.py`

**Step 1:** 验证:
- `CC` 有多个 sense（连接确认、CC阻值等）
- `CP` 有多个 sense（控制导引功能、CP占空比等）
- `PE` 有多个 sense
- 已知唯一缩写不触发澄清
- 带上下文时不触发澄清

---

## 验证和收尾

### Task V1: 全量回归测试

运行全部测试确认无回归:
```
pytest -q tests/
pytest -q -m integration
```

### Task V2: 更新架构文档

- 更新 `docs/kb1_current_architecture_2026-04-28.md` 中的"当前已知边界"和"后续路线"
- 标记已完成的里程碑

### Task V3: 提交

```
git add -A
git commit -m "feat: complete P1-P4 - retrieval quality baseline, parameter_value policy, process model, KB-driven ambiguity"
```