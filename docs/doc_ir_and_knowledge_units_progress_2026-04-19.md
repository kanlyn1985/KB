# DocIR 与知识单元抽取推进记录

## 当前已落地

### 1. DocIR

已新增：

- `src/enterprise_agent_kb/doc_ir.py`

当前 `parse_document()` 已同时输出：

- `normalized/{doc_id}.json`
- `normalized/{doc_id}.doc_ir.json`

### 2. 清洗与阅读顺序骨架

已新增：

- `src/enterprise_agent_kb/layout_cleaner.py`
- `src/enterprise_agent_kb/reading_order.py`

当前 `parse_document()` 已额外输出：

- `normalized/{doc_id}.cleaned_doc_ir.json`

### 3. 结构恢复骨架

已新增：

- `src/enterprise_agent_kb/structure_recovery.py`

当前可从 `doc_ir` 中恢复章节骨架。

### 4. 知识单元抽取最小版

已新增：

- `src/enterprise_agent_kb/knowledge_units.py`

当前支持抽取：

- `definition`
- `requirement`
- `table_requirement`

---

## 当前效果

对 `DOC-000007`：

- `doc_ir` 已生成
- `cleaned_doc_ir` 已生成
- `knowledge_units` 可抽出 `81` 个知识单元

其中包含：

- 术语定义单元
- 规范要求单元
- 表格要求单元

---

## 当前问题

当前知识单元抽取仍属于“最小可用版”，已知问题包括：

1. `definition` 规则过宽
   - 部分引用文件或表题会被误判为 definition

2. `table_requirement` 仅做最近标题绑定
   - 还没有恢复稳定的表题/章节归属

3. `requirement` 规则仍是句子级触发
   - 还没有 subject / condition / threshold 的结构拆分

4. 尚未覆盖：
   - `procedure`
   - `formula`
   - `figure_knowledge`

---

## 建议的下一步

### 下一优先级 1

改进 `knowledge_units.py` 过滤规则：

- 收窄 definition 判定
- 避免引用文件被当作 definition
- 表格标题与表格绑定

### 下一优先级 2

新增 `procedure` 抽取：

- 识别“试验方法”“步骤”“a）b）c）”
- 输出 `procedure` 单元

### 下一优先级 3

把知识单元写成正式产物：

- `normalized/{doc_id}.knowledge_units.json`
- `kb.jsonl`

这样后续可直接用于：

- facts 增强
- 检索增强
- 向量化入库

---

## 结论

目前已经从“只有 PDF -> blocks”推进到了：

`PDF -> doc_ir -> cleaned_doc_ir -> structure skeleton -> knowledge units`

这已经是新方案的主干雏形。  
后续重点不再是有没有中间层，而是：

- 提高知识单元抽取质量
- 增加 `procedure / formula / figure_knowledge`
- 让 knowledge units 真正反哺 facts 与 retrieval

