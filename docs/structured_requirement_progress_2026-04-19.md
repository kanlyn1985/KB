# Requirement 结构化进展记录

## 当前已实现

在 `knowledge_units.py` 中，`requirement` 已从纯文本段升级为带结构字段的知识单元。

当前字段包括：

- `id`
- `type`
- `title`
- `content`
- `section`
- `page`
- `subject`
- `condition`
- `threshold`

---

## 当前效果

对 `DOC-000007`，已经可以抽出类似下面的结构化要求：

### 示例 1

- `title`: `4.4 材料`
- `content`: `逆变器所有的有害材料含量应不超过SJ/T 11363的限量要求。`
- `subject`: `材料`
- `threshold`: `不超过SJ/T 11363的限量要求`

### 示例 2

- `title`: `4.5.2 输出特性参数允差。`
- `content`: `输入直流电路电压在正常（未触发输入欠压或过压保护功能）范围的情况下，应满足下述规定：`
- `subject`: `输出特性参数允差`
- `condition`: `在正常（未触发输入欠压或过压保护功能）范围的情况下`
- `threshold`: `应满足下述规定：`

### 示例 3

- `title`: `4.5.2 输出特性参数允差。`
- `content`: `输出频率允差应不超过额定输出频率的 ±1 Hz。`
- `subject`: `输出特性参数允差`
- `threshold`: `不超过额定输出频率的 ±1 Hz`

---

## 当前局限

当前这套结构化还是规则版，主要限制有：

1. `subject` 主要来自标题，而不是句内主语解析
2. `condition` 目前只提取常见句式：
   - `在 ... 情况下`
   - `当 ... 时`
   - `对于 ...`
3. `threshold` 目前只提取显式阈值短语：
   - `不超过 ...`
   - `不小于 ...`
   - `应符合 ...`
   - `应满足 ...`

还没有做到：

- 单句多条件拆分
- 单句多阈值拆分
- 数值单位标准化
- 主体对象统一命名
- requirement 与 table_requirement 融合

---

## 下一步建议

### 1. 数值标准化

新增：

- `normalized_threshold_value`
- `normalized_threshold_unit`

例如：

- `±1 Hz`
- `0.5 mA`
- `85%`

### 2. 主体标准化

将 `subject` 从标题短语升级为：

- `逆变器`
- `输出电压允差`
- `输入欠压保护`

### 3. 表格要求融合

将 `table_requirement` 中表头/单元格进一步映射到：

- `parameter`
- `value`
- `condition`

### 4. requirement 与 facts 联动

后续可以考虑将结构化 requirement 直接反哺为新的 facts 类型：

- `requirement`
- `constraint`
- `threshold`
- `parameter_value`

---

## 结论

当前 requirement 已经从“可展示文本段”升级成“初步可计算结构”。  
这意味着后续可以不再只依赖全文 embedding，而是逐步转向：

- 条件化检索
- 阈值对比
- 约束类问答
- 要求项验证

