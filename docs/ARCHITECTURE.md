# KB-Ontology 架构

**状态**: 设计已确认（2026-07-24 grill session）
**关联 ADR**: 0001-0006

## 1. 系统定位

**Agent 知识后端**——把文档内容萃取进 Ontology，查询时返回带判断力的 ContextPack。

系统接收文档，经 LLM 萃取为结构化知识（Entity + Attribute + Relation），存入本体图谱。查询时经 LLM 理解意图，由确定性查询模板遍历本体，返回结构化知识 + 证据 + 判断。

详见 `CONTEXT.md`。

## 2. 核心链路

```
干净文本（外部预处理后）
  ↓
LLM 萃取引擎（按 Domain Pack 定义的 Class/Relation schema）
  ↓
Ontology 存储（关系型表）
  ↓
LLM 查询理解 → QueryFrame
  ↓
查询模板引擎（按 intent 选模板，确定性执行）
  ↓
规则判断（证据充分性/歧义/缺口）→ 必要时 LLM 语义判断
  ↓
ContextPack → Agent
```

## 3. 组件清单

### 3.1 核心组件（全新编写）

| 组件 | 职责 | 状态 |
|------|------|------|
| Domain Pack Schema | 定义 Class/Relation/Attribute 模板 + 唯一性规则 | 已完成 |
| LLM 萃取引擎 | 读文档 → 按 schema 萃取 Entity/Attribute/Relation | 已完成 |
| Ontology 存储 | entities/attributes/relations/evidence 四表 | 已完成 |
| 查询模板引擎 | 按 intent 选择并执行预定义查询 | 已完成 |
| 判断力层 | 规则判断 + LLM 语义判断 | 已完成 |
| ContextPack 组装 | 聚合查询结果 + 判断 → 输出 | 已完成 |

### 3.2 可复用组件（从 agent_kb_core 复制并适配）

| 组件 | 来源 | 复用内容 | 状态 |
|------|------|----------|------|
| LLM 客户端 | `llm/llm_client.py`（已扩展） | Anthropic Messages + OpenAI Chat Completions；默认 **krill / grok-4.5** | 已完成 |
| QueryFrame / ContextPack | 按 ontology 重写 | 查询理解 + Agent 主输出 | 已完成 |
| 安全模块 | `security/` | API-key auth / RBAC / secrets / SQLite audit / tenant DB router | 已完成 |
| 服务层 | `service/` | `OntologyService` + trusted/secure HTTP（health/query/extract/metrics/audit/OpenAPI） | 已完成 |
| 运行时 | `runtime/` | 进程内 token-bucket 限流（job/worker 延后） | 精简完成 |
| 可观测性 | `observability/` | MetricsRegistry + Tracer + 可选 OTLP exporter | 已完成 |
| 部署 | `Dockerfile` + `deploy/` | Compose + K8s Deployment 骨架 | 已完成 |

## 4. 数据模型

### 4.1 Ontology 存储四表

```
entities
  id            TEXT PRIMARY KEY
  class         TEXT NOT NULL          # Domain Pack 定义的 Class 名
  canonical_name TEXT NOT NULL         # 主显示名
  status        TEXT NOT NULL          # active / pending / merged
  created_at    TEXT NOT NULL

attributes
  id            TEXT PRIMARY KEY
  entity_id     TEXT NOT NULL → entities.id
  name          TEXT NOT NULL          # 属性名（来自 Class 属性模板）
  value         TEXT                   # 序列化存储
  value_type    TEXT NOT NULL          # number/string/boolean/entity_ref
  confidence    REAL
  created_at    TEXT NOT NULL

relations
  id            TEXT PRIMARY KEY
  source_id     TEXT NOT NULL → entities.id
  relation_type TEXT NOT NULL          # part_of/references 或 domain pack 定义
  target_id     TEXT NOT NULL → entities.id
  confidence    REAL
  created_at    TEXT NOT NULL

evidence
  id            TEXT PRIMARY KEY
  ref_type      TEXT NOT NULL          # entity/attribute/relation
  ref_id        TEXT NOT NULL          # 指向对应表的 id
  document_id   TEXT NOT NULL
  text_span     TEXT                   # 原文摘录
  location      TEXT                   # 位置标记（页码/段落/字符偏移）
  confidence    REAL
  created_at    TEXT NOT NULL
```

### 4.2 Domain Pack Class 定义格式

```
class: Parameter
  description: 工程参数，有量化值和测量条件

  attribute_template:
    name:      string, required
    value:     number, optional
    unit:      string, optional
    operator:  enum(<=, >=, =, >, <), optional
    condition: string, optional

  relation_roles:
    - part_of: [Product, Subsystem]        # 可属于产品或子系统
    - verified_by: [Method]                # 可被方法验证

  identity_rule: name + condition 相同视为同一 Entity

  display: primary=name, secondary=[value, unit, operator]
```

### 4.3 关系类型分层

```
Core 骨架（所有领域共享）:
  part_of       # 部分-整体，构建层级
  references    # 引用关系，跨实体连接

Domain Pack 扩展（领域特有）:
  obc_dcdc:     verified_by, constrained_by, defined_in
  legal:        governed_by, obligated_by, terminated_by
```

## 5. 查询执行

### 查询链路

```
用户查询
  → LLM 理解 → QueryFrame {intent, target_entity, target_attributes, ...}
  → 查询模板引擎按 intent 选模板
  → 确定性查询 Ontology 存储
  → 规则判断（结构层：条数/目标/冲突）
  → 判定"有疑问" → LLM 语义判断（质量/缺口/策略）
  → 组装 ContextPack
```

### 查询模板（初始集合）

| intent | 模板逻辑 | 场景 |
|--------|----------|------|
| parameter_lookup | 按 entity_id 取 attributes | "DCDC输出纹波限制是多少？" |
| definition | 按 entity_id 取 description + 关联实体 | "什么是车载充电机？" |
| relation_query | 按 source+type 取 relations | "DCDC有哪些测试方法？" |
| hierarchy_traversal | 递归 part_of | "OBC包含哪些子系统？" |
| cross_entity | 查两实体间 relation | "ISO 14229和GB/T 18487什么关系？" |
| attribute_search | 按 attribute value 反查 entity | "哪些参数和温度有关？" |

## 6. 实施顺序

```
Phase 1: Domain Pack Schema 定义
  → 定义 Class 结构格式
  → 编写第一个 domain pack（obc_dcdc）

Phase 2: Ontology 存储
  → 建四表 schema
  → CRUD 接口

Phase 3: LLM 萃取引擎
  → prompt 设计
  → 文档→Entity/Attribute/Relation 萃取
  → 唯一性合并

Phase 4: 查询模板引擎
  → 6 个初始模板
  → QueryFrame → 模板映射

Phase 5: 判断力层
  → 规则判断实现
  → LLM 语义判断接入

Phase 6: ContextPack 组装 + 复用模块集成  ✅
  → 安全 / 服务 / 可观测 / 部署骨架
  → trusted + secure HTTP、CLI、MCP stdio
  → 端到端验证（pytest + live smoke）
```

**Phase 6 完成标准**：库路径 `answer_query`、HTTP `/v1/query`、CLI `query`、MCP `kb_ontology_query` 均返回同一形状的 ContextPack；安全路径具备 API-key + RBAC + audit；部署可用 Compose 起 secure-serve。

**后续 hardening（已部分落地）**：
- ✅ SQLite job queue（`runtime/jobs.py`）+ `extract_document` 批入队/worker
- ✅ CLI：`extract-batch` / `worker-once` / `worker-run` / `jobs`
- ✅ HTTP：`/v1/jobs`、`/v1/jobs/extract-batch`、`/v1/jobs/worker-once`
- ✅ `scripts/ingest_athena_sample.py`（Athena raw 抽样入队）
- ✅ Athena curated batch 落地 + stub/noise 过滤（`min_bytes` / `SKIP_RELATIVE_PATHS` / CJK heuristic）
- ✅ 查询质量：terminology 别名扩展、noise strip（工作原理/拓扑）、compact resolve、mention 最长命中、resolve 失败 fallback peel
- ✅ 空萃取不再静默成功（`EmptyExtractionError` → job 重试/失败）；enqueue 默认 `text_limit=8000`
- ✅ Athena wave-2（G5 策略类文档）入队并抽完；样例库约 251e / 851a / 376r / 1120ev
- 仍延后：分布式限流、MCP HTTP transport、多 Domain 并行 worker 池、生产 readiness 密钥管理、全文 chunking

## 7. 文件结构（现状）

```
kb-ontology/
├── CONTEXT.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── adr/0001–0006
├── src/kb_ontology/
│   ├── llm/                 # Anthropic + OpenAI(krill)
│   ├── domains/             # Domain Pack schema + loader
│   ├── extraction/          # LLM 萃取引擎
│   ├── storage/             # Ontology 四表
│   ├── query/               # QueryFrame + 6 templates
│   ├── judgement/           # 规则优先 + LLM 语义兜底
│   ├── context/             # ContextPack
│   ├── pipeline.py          # answer_query
│   ├── security/            # auth / secrets / audit
│   ├── service/             # OntologyService + HTTP
│   ├── adapters/            # MCP tools + stdio JSON-RPC
│   ├── runtime/             # token-bucket 限流 + SQLite job queue
│   ├── ingestion/           # discover + enqueue + extract worker
│   ├── observability/       # metrics + tracer
│   └── cli.py               # serve / mcp / query / extract / extract-batch / worker-* / jobs
├── domains/{generic,obc_dcdc}/
├── scripts/ingest_athena_sample.py
├── deploy/{docker-compose.yml,kubernetes/}
├── Dockerfile
├── tests/
└── pyproject.toml           # console script: kb-ontology
```
