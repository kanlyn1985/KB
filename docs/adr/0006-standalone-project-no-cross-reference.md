# 系统作为独立项目存在，不引用旧系统代码

kb-ontology 是完全独立的项目，位于 `/home/evt/projects/kb-ontology/`。不从 KB1 仓库的 `agent_kb_core` 或 `enterprise_agent_kb` 引用任何代码。可复用的文件（LLM 客户端、安全模块、部署配置等）直接复制过来，不做 import 跨项目依赖。

**为什么**：KB1 仓库已经非常混乱——旧系统（enterprise_agent_kb）、新内核（agent_kb_core）、桥接层（kb1_ontology）三套代码并存，文档全部描述旧系统，路径是 Windows 格式。在旧仓库里改造会持续受到噪声干扰。独立项目从干净的基线开始。

**可复用清单**（复制到新项目）：
- LLM 客户端（Anthropic 兼容，零依赖）
- 安全模块（auth/RBAC/secrets/audit）
- 部署配置（Docker/K8s/Compose）
- 运行时（worker/job/leader lease）
- 可观测性（metrics/telemetry）
- 服务层（HTTP API/MCP adapter/OpenAPI）

**不复用、重新写的核心部分**：
- Ontology 存储 schema（全新四表）
- LLM 萃取管线（文档→ontology 核心链路）
- 查询模板引擎（按 intent 查 ontology）
- Domain Pack Class 定义格式（扩展属性模板/关系角色/唯一性）
- 判断力层（规则 + LLM）

**数据迁移**：Athena markdown 和旧 normalized JSON 通过外部预处理脚本转换为干净文本后接入，不直接读取旧数据库。
