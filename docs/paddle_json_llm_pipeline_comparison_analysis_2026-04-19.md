# Paddle JSON + 局部 LLM 修复方案对比分析

## 1. 结论先行

你给的新方案方向是对的，而且和当前项目暴露出来的核心问题高度一致。  
当前项目的主要问题不是“有没有 OCR”，而是：

- PDF 解析结果过早被压平
- 中间层过弱
- 页面结构、标题树、条款树、图表归属没有系统恢复
- facts 抽取直接建立在“弱结构文本块”上
- 一旦 Paddle 输出不完整，后续层几乎没有修复抓手

你提出的方案本质上是在当前链路中补上一个关键缺失层：

`Paddle JSON -> DocIR -> 结构恢复 -> 知识单元抽取 -> 局部 LLM 修复`

这比当前系统的：

`PDF -> block markdown/text -> evidence -> facts`

更适合标准/规范类文档。

所以结论是：

1. 新方案值得采用  
2. 不建议整体推翻当前系统  
3. 建议以“替换 parse 后半段 + 增强 facts 上游结构层”的方式渐进接入

---

## 2. 当前实现现状

当前项目 PDF 处理主链路位于：

- [parse.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/parse.py)
- [quality.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/quality.py)
- [evidence.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/evidence.py)
- [facts.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/facts.py)

### 当前做法

当前链路大致是：

```text
PDF
-> opendataloader / PaddleVL / PyMuPDF
-> normalized/{doc_id}.json
-> pages + blocks
-> evidence
-> facts
```

### 当前优势

- 已支持多级解析 fallback
- 已支持 PaddleVL 作为图片型 PDF 二级解析器
- 已支持异常文本层检测
- 已打通 quality / evidence / facts / wiki / retrieval / answer 闭环

### 当前主要缺点

#### 2.1 缺少统一中间层语义抽象

现在 `normalized/*.json` 更像“解析结果落盘”，不是“文档结构处理中间层”。

问题：

- block 类型语义不足
- 后续结构处理没有统一 schema
- parser vendor 输出格式直接影响后面逻辑

#### 2.2 结构恢复能力不足

当前虽然有 `section_heading` 抽取，但并没有真正恢复：

- 标题树
- 条款树
- 附录树
- 图表归属
- 公式归属
- 表格归属

这会导致：

- 表格类要求被打平
- 试验步骤条款与上级标题脱离
- V2X / V2G 这种术语和条款上下文绑定不稳

#### 2.3 表格/公式/图片信息损失较大

目前 Paddle 路径主要把整页 markdown 当成一个 `ocr_markdown` block。

问题：

- 表格 cell 结构没有稳定保留
- 公式没有独立块级语义
- 图片区域和正文关系没有系统绑定
- 图题、表题、正文引用关系丢失

#### 2.4 清洗和阅读顺序恢复不够系统

当前系统对：

- 页眉页脚
- 页码
- 断行
- 多块阅读顺序
- 表题/图题归属

没有独立处理层，而是分散在后续抽取规则里被动承受。

#### 2.5 LLM 增强没有进入解析链路

当前 LLM 主要用于：

- 查询理解
- 回答策略
- 诊断和测试扩展

但没有进入 PDF 结构修复层。  
而你提出的新方案恰好把 LLM 放到了更合理的位置：

- 不负责全文转换
- 只负责局部修复

这是非常关键的思路。

---

## 3. 新方案的价值

你给的方案最有价值的地方，不是“Paddle + LLM”这四个字，而是它明确分层了。

### 3.1 把“看见结构”和“恢复结构”分开

新方案中：

- Paddle 负责识别
- 规则负责恢复
- LLM 负责修复杂例

这比“一个模型直接转 Markdown”稳定得多。

### 3.2 引入 DocIR 是关键改进

这是新方案里最值得采用的部分。

DocIR 会带来三个直接收益：

1. OCR 供应商可替换  
2. 后续清洗、结构恢复、知识抽取都依赖统一 schema  
3. 可以做独立测试和局部调试

这正好补上当前系统的薄弱点。

### 3.3 让结构恢复成为显式阶段

新方案明确要求恢复：

- 标题树
- 条款树
- 图表公式归属

这会直接提升：

- requirement 抽取稳定性
- procedure 抽取稳定性
- comparison / scope / constraint 问答质量

### 3.4 把知识单元抽取从“段落级”升级到“语义单元级”

你方案里的这些类型非常有价值：

- `definition`
- `requirement`
- `table_requirement`
- `procedure`
- `formula`
- `figure_knowledge`

这正是当前项目 facts 类型仍然不足的地方。

### 3.5 把 LLM 放在局部修复层是合理的

结合我前面做的真实测试，当前项目配置的 LLM **不适合直接做 PDF/图片直读**。  
但如果它只负责：

- 表格修复
- 标题纠偏
- 图示解释
- 公式补齐

那是可行的，而且更节省 token 和成本。

---

## 4. 新方案与当前系统的映射关系

## 4.1 可以直接复用的部分

这些部分无需推翻：

- `documents / pages / blocks / evidence / facts / wiki / graph` 总体存储框架
- `quality.py`
- `evidence.py`
- `facts.py` 的后半段事实入库逻辑
- `retrieval / query_context / answer_query`
- `generated_tests`
- `demo / api_server / cli`

也就是说，现有项目的“知识库后半段”基本都能保留。

## 4.2 需要重构/新增的部分

重点改造的是 parse 上游到 facts 上游这一段：

### 必须新增

- `doc_ir.py`
- `doc_ir_builders/`
- `layout_cleaner.py`
- `reading_order.py`
- `structure_recovery.py`
- `knowledge_units.py`
- `llm_repair.py`

### 必须改造

- `parse.py`
- `facts.py`
- 可能还包括 `quality.py` 的输入层

---

## 5. 推荐落地方式

## 5.1 不建议一次性替换 parse.py

原因：

- 风险太高
- 当前系统后半段已经能跑
- 一次性替换不利于对比回归

## 5.2 建议采用“双轨解析”

推荐做法：

### 轨道 A：保留当前 parse 链路

作为现有生产链路。

### 轨道 B：新增 DocIR 试验链路

```text
PDF
-> Paddle raw json
-> doc_ir.json
-> cleaned_doc_ir.json
-> structured_doc_ir.json
-> kb_units.jsonl
-> 再进入 evidence/facts
```

这样可以：

- 同文档对比两套结果
- 量化提升
- 渐进切换

---

## 6. 建议的目标架构

推荐未来改成：

```text
PDF
-> parser adapters
   -> paddle_raw.json
-> DocIR builder
   -> doc_ir.json
-> cleaner / reading order
   -> cleaned_doc_ir.json
-> structure recovery
   -> structured_doc_ir.json
-> knowledge unit extraction
   -> kb_units.jsonl
-> local LLM repair for hard cases
-> evidence / facts / entities / wiki / graph
-> retrieval / answer / diagnostics / tests
```

这意味着：

- `parse.py` 不再直接产出“最终 normalized pages”
- 而是产出“parser raw + DocIR”

---

## 7. 与当前问题的直接对应关系

### 7.1 “很多信息丢失”

新方案对应修复点：

- Paddle raw 保留
- DocIR 保留 block 语义
- 表格/图片/公式独立块
- 图表公式归属恢复

### 7.2 “标题层级经常错”

新方案对应修复点：

- 标题识别规则层
- 条款树恢复层
- 局部 LLM 标题纠偏

### 7.3 “表格要求检索效果差”

新方案对应修复点：

- table block 独立
- table_requirement 抽取
- 表题与章节绑定

### 7.4 “试验方法和步骤容易散掉”

新方案对应修复点：

- reading order 恢复
- procedure 类型知识单元

### 7.5 “图片/图示相关信息丢失”

新方案对应修复点：

- figure block
- caption 绑定
- figure_knowledge 抽取
- LLM 局部图示解释

---

## 8. 建议新增的知识单元与 facts 对齐关系

建议把你方案里的知识单元，映射到当前 facts 扩展方向：

| 知识单元 | 可对应 fact 方向 |
|---|---|
| definition | `term_definition`, `concept_definition` |
| requirement | `requirement`, `constraint`, `threshold` |
| table_requirement | `parameter_value`, `threshold`, `requirement` |
| procedure | `procedure_step`, `test_procedure` |
| formula | `formula_definition`, `parameter_relation` |
| figure_knowledge | `figure_relation`, `system_structure` |

这和我们前面已经在做的“facts 扩展”路线是一致的。

---

## 9. 推荐实施顺序

### Phase 1：最低风险接入

1. 保留当前 parse.py
2. 新增 `paddle_raw.json` 落盘
3. 新增 `doc_ir.json`
4. 新增 `raw.md` 供人工校验

目标：

- 先建立可追溯中间层

### Phase 2：结构恢复

1. 去页眉页脚
2. 阅读顺序恢复
3. 标题树/条款树恢复
4. 图表标题绑定

目标：

- 解决“结构丢失”

### Phase 3：知识单元抽取

1. `definition`
2. `requirement`
3. `table_requirement`
4. `procedure`

目标：

- 提升问答性和检索质量

### Phase 4：LLM 局部修复

只对以下 block 触发：

- 表格损坏
- 复杂公式
- 图示块
- 标题层级不确定

目标：

- 低成本补齐复杂结构

---

## 10. 实施建议

结合当前项目，我建议不要再继续在现有 `parse.py` 上堆零散规则，而是直接开始这三步：

1. 先做 `DocIR`
2. 再做 `structure_recovery`
3. 再做 `knowledge_units`

也就是说，真正优先级最高的是：

- 不是直接“上 LLM”
- 而是先把 `Paddle JSON -> DocIR` 做出来

因为没有这个中间层，后面所有修复都只能在弱结构文本上打补丁。

---

## 11. 最终判断

这份新方案与当前项目并不冲突，反而是当前项目下一阶段最合理的演进方向。  
如果只用一句话总结：

**当前系统已经把“知识库后半段”做好了，但“PDF 到结构化知识单元”的前半段还不够强；你这份方案正好补的是前半段。**

所以我建议：

- 采用这份方案
- 但以“渐进式替换 parse 上游”的方式落地
- 优先实现 `paddle_raw.json -> doc_ir.json -> structure_recovery`

这会比继续在当前 parse 结果上修修补补更值得。

