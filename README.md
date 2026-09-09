# KB1 — Evidence-grounded Agent Knowledge Base

企业级智能体知识库。当前活跃项目是 **Agent KB Core**（`agent_kb_core/`）——一个通用证据约束型知识库编译框架，配合 RFLP 本体树（`docs/ontology/`）做节点级召回与证据约束式问答。

## 目录地图

| 路径 | 说明 |
|---|---|
| `agent_kb_core/` | 活跃项目：`agent_kb` 包 + Web UI + 落位/评测工具 |
| `docs/ontology/` | RFLP 本体树骨架、文档落位数据、节点卡、golden cases、查询理解设计 |
| `corpus/` | 源文档语料（标准 PDF、需求 xlsx/docx、Athena 团队语料） |
| `archive/` | 已归档的旧系统（legacy `enterprise_agent_kb`、旧 `kb1_ontology` 设计） |
| `.github/` | CI（`agent-kb-core.yml` / `tests.yml`） |

## 快速开始

详见 [`agent_kb_core/README.md`](agent_kb_core/README.md)。

```bash
# 运行测试
cd agent_kb_core && python -m pytest

# 起 Web UI
python agent_kb_core/webui/server.py --db agent_kb_core/node-index.sqlite3 \
    --domain-dir agent_kb_core/domains/obc_dcdc --port 8080
```

## 当前状态

- package `0.5.0`，Core schema `v8`
- 骨架树 `skeleton_v0.4.json`（210 节点，tree_version 0.4.0）
- golden cases 30 个，正式管线 Hit@10 = 100%
- 查询理解：规则 + LLM 混合（`use_llm=True`），证据约束式答案生成（`answer-query`）
