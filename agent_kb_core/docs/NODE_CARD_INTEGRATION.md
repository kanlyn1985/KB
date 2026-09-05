# 节点卡正式接入（2026-08-18）

把骨架节点卡（209 张，245,976 落位单元聚合）正式接入 agent_kb_core
生产索引，使 `query-production` 按节点级召回。

## 背景

此前召回不准的根因：索引只有"文本碎片投影"，没有骨架节点卡。
现通过 `import-node-cards` 命令把节点卡 + 参数对象投影写入 SQLite 生产索引。

## 使用

```bash
# 1. 构建节点卡（从落位数据聚合，已生成 node_cards.jsonl）
python agent_kb_core/validation/build_node_cards.py

# 2. 导入生产索引（含词法 + 向量）
cd agent_kb_core
python -m agent_kb.cli import-node-cards \
  --db node-index.sqlite3 \
  --node-cards ../docs/ontology/tree_skeleton/llm_landing/node_cards.jsonl \
  --domain-dir domains/obc_dcdc

# 3. 查询（必须带 --domain-dir，术语映射是召回正确性的前提）
python -m agent_kb.cli query-production \
  --db node-index.sqlite3 \
  --query "帮我介绍一下OBC的工作原理" \
  --domain-dir domains/obc_dcdc
```

## 验证结果

- 导入：216 对象（210 节点 + 6 参数）/ 216 卡片 / 209 facts / 4,829 evidence / 5,470 向量
- 正式管线 golden-case 评测（15 个跨领域查询）：**Hit@10 = 100%**
- 证据判定：**sufficient 8/15**（知识/原理/安全类查询；参数/方法类为 partial，属正常保守）
- 33 个单元测试全绿

## 证据链（v2，2026-08-18 补充）

节点卡导入时为每个节点生成：
- **evidence**：聚合内容拆成单元级证据（每节点最多 24 条，snippet=落位单元文本）
- **fact**：每节点 1 条 `term_definition`（subject=节点 ID，绑定 evidence）
- **卡片 evidence_ids**：指向该节点 evidence

效果：查询"OBC 工作原理"从 `insufficient(0.10)/ask_clarification_or_abstain`
提升到 `sufficient(0.88)/answer_with_evidence`——系统现在能基于证据作答。

## 关键注意事项

1. **必须传 `--domain-dir`**：不带 domain pack 时无法做术语映射，
   召回退化为原始词法匹配（DCDC 参数卡错误胜出）。
2. **节点卡覆盖术语投影**：同 ID 节点（如 P-KNOW-OBC 同时在术语表和节点卡）
   以节点卡为准（含聚合内容）。
3. 节点卡内容截断：search_text 取内容前 2000 字符（保证 FTS 索引效率）。

## 文件

- `src/agent_kb/commands/import_node_cards.py`（导入命令实现）
- `src/agent_kb/cli.py`（注册 import-node-cards）
- `validation/build_node_cards.py`（落位 → 节点卡）
- `validation/eval_node_recall.py`（内存评测，100%）
- `docs/ontology/tree_skeleton/llm_landing/node_cards.jsonl`（节点卡数据）
- `docs/ontology/tree_skeleton/llm_landing/golden_cases.json`（15 个 golden cases）
