# Knowledge Units 推进记录

## 当前已落地

已新增：

- `src/enterprise_agent_kb/knowledge_units.py`

当前支持的知识单元类型：

- `definition`
- `requirement`
- `table_requirement`
- `procedure`

并且已支持正式输出：

- `knowledge_base/normalized/{doc_id}.knowledge_units.json`
- `knowledge_base/normalized/{doc_id}.kb.jsonl`

---

## 真实运行结果

对 `DOC-000007`：

- 已成功输出 `DOC-000007.knowledge_units.json`
- 已成功输出 `DOC-000007.kb.jsonl`
- 当前共抽取 `145` 个知识单元

类型分布：

- `table_requirement`: 5
- `procedure`: 92
- `definition`: 3
- `requirement`: 45

---

## 当前问题

当前 `procedure` 抽取明显偏宽，已经把：

- 前言
- 引用文件
- 一些普通说明句

也吸进去了。

这说明：

- 目前 `procedure` 规则还只是“最小可用版”
- 还不能直接作为最终质量版本

### 当前根因

当前 procedure 触发词过宽，例如：

- `按照`
- `进行`
- `测量`
- `检查`

这些词在标准文档中出现频率太高，不能单独作为强特征。

---

## 现阶段价值

虽然当前 `procedure` 质量还不够好，但这一步已经有三个重要价值：

1. 知识单元产物格式已经固定
2. 系统已经能从 `cleaned_doc_ir` 输出 `kb.jsonl`
3. 后续只需要迭代抽取质量，不需要再改产物格式

换句话说，当前已经完成了从：

`PDF -> doc_ir -> cleaned_doc_ir -> knowledge_units`

这一主链路的首次贯通。

---

## 下一步建议

### 优先级最高

收紧 `procedure` 规则，建议只在以下条件下抽取：

- 当前章节位于 `5 试验方法`
- 或 heading/title 包含：
  - `试验`
  - `试验方法`
  - `步骤`
  - `检查`
- 段落本身包含：
  - `按照 ... 进行试验`
  - `在输入端施加`
  - `测量`
  - `连接`
  - `记录`
  - `使用 ... 检查`

并降低：

- 前言
- 引用文件
- 纯背景说明

被识别为 procedure 的概率。

### 第二优先级

增加更细粒度结构：

- `requirement.subject`
- `requirement.condition`
- `requirement.threshold`

让 requirement 从“文本段”进化成“结构化要求”。

### 第三优先级

增加：

- `formula`
- `figure_knowledge`

使标准文档的图表/公式信息不再丢失。

---

## 结论

当前 `knowledge_units` 已经具备“产物层可用性”，但还不具备“抽取质量最终可用性”。  
接下来最重要的工作不是新增更多类型，而是把：

- `procedure`
- `definition`
- `table_requirement`

这三类抽取规则打磨稳定。

