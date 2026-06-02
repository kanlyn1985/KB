# Query Repair Phase 0 Execution Spec

## 文档定位

这份规格文档只服务于一个目标：

> 在不进入大规模重构、不补知识库的前提下，先止住“类型对了、主题还错着”的系统性失真。

它承接：

- [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md)
- [query_repair_blueprint_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_blueprint_2026-04-23.md)
- [query_repair_task_breakdown_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_task_breakdown_2026-04-23.md)

---

## 一、Phase 0 的唯一目标

Phase 0 不追求“所有问题都答对”，只追求一件事：

> 让 query 理解链路内部自洽。

这里的“自洽”具体指：

1. `query_type`、`normalized_query`、`target_topic`、`must_terms` 之间不能互相打架
2. 一旦规则修正了 query type，topic anchor 必须同步被修正
3. 解释型问法不能再轻易掉进 `general_search`
4. 细粒度限定词不能在 rewrite 阶段被吃掉

如果这一阶段没做好，后面 topic resolution、retrieval、answer policy 的工作都会围绕错主题做优化。

---

## 二、Phase 0 的范围边界

### 范围内

- semantic parser 输出质量约束
- rewrite 两阶段重构
- 解释型问法识别扩展
- 限定词保护机制
- 最小调试字段输出

### 范围外

- topic resolution 排序修复
- retrieval routing 调整
- answer policy 重构
- wiki / fact / entity 补齐
- UI 改造

原因：

Phase 0 只负责把“输入理解”变对，不负责把“答案表现”做到最好。

---

## 三、Phase 0 需要消除的现象

### 现象 A

query type 看起来对了，但 `target_topic` 还是粗主题。

示例：

- `CC阻值代表什么意思`
  被识别成参数类，但 `target_topic = CC`

### 现象 B

解释型问法掉到 `general_search`

示例：

- `V2V的定义是什么`
- `CP占空比表示什么`

### 现象 C

semantic parser 高置信输出明显坏结果

示例：

- `target_topic = undefined`
- `query_type = no_answer_candidate`
- `normalized_query` 为空或只剩不合理碎片

### 现象 D

must_terms 丢失细粒度锚点

示例：

- 原问题有 `CC阻值`
- 结果 `must_terms` 里只剩 `CC`

---

## 四、Phase 0 交付物

Phase 0 必须交付的不是代码本身，而是以下 4 类能力。

### 交付物 1：一致性的 rewrite 输出

最终 rewrite 对象至少保证：

- `query_type` 与 query 意图一致
- `target_topic` 与 `must_terms` 语义一致
- `normalized_query` 不得比 `target_topic` 更粗

### 交付物 2：解释型问法覆盖

以下问法进入稳定的定义/参数解释链路：

- `是什么意思`
- `代表什么意思`
- `表示什么`
- `指什么`
- `含义是什么`

### 交付物 3：限定词保护

系统可以识别并保护：

- `CC阻值`
- `CP占空比`
- `检测点1电压`
- `R4c'`

### 交付物 4：最小观测字段

Phase 0 完成后，单次 query 至少可看到：

- `final_query_type`
- `final_normalized_query`
- `final_target_topic`
- `protected_anchor_terms`
- `rewrite_override_applied`
- `semantic_quality_flags`

---

## 五、实施任务顺序

## Step 1：约束 semantic parser 的坏输出

目标：

先减少语义解析器输出明显坏结果的概率。

处理重点：

1. 不允许 `target_topic = undefined`
2. 不允许高置信输出 `no_answer_candidate`，除非 query 确实无效
3. 对“解释型问法”增加显式约束

为什么先做这步：

因为如果 semantic parser 持续产出明显坏结果，rewrite 层会一直背锅。

阶段完成标志：

- 典型 query 不再出现 `undefined`
- `no_answer_candidate` 只出现在真正空洞或无意义 query 上

---

## Step 2：拆 rewrite 为两阶段

目标：

把“意图判定”和“主题锚点构造”拆开。

阶段 1：

- 最终确定 `query_type`

阶段 2：

- 基于最终 `query_type` 重构 `normalized_query / target_topic / must_terms`

为什么这是核心：

当前最关键的系统 bug，就是这两步混在了一起，导致只有 query type 被修正，topic 没修正。

阶段完成标志：

- 一旦 `query_type` 被 override，`target_topic` 也跟着变化
- 不再出现“parameter_lookup + target_topic=CC”这种半错状态

---

## Step 3：补解释型问法规则

目标：

让解释型问法稳定进入定义/参数解释路径。

需要覆盖的模板：

- `X是什么意思`
- `X代表什么意思`
- `X表示什么`
- `X指什么`
- `X含义是什么`

阶段完成标志：

- 这些问法不再落入 `general_search`
- 规则层和 semantic 层对这类 query 的判定方向一致

---

## Step 4：加限定词保护机制

目标：

保证细粒度锚点不在 rewrite 中退化。

保护对象类型：

1. 缩写 + 参数词
2. 缩写 + 属性词
3. 检测点 + 编号 + 属性
4. 参数符号 + 特殊后缀

阶段完成标志：

- 输出 `protected_anchor_terms`
- `target_topic` 至少保留一个受保护锚点

---

## Step 5：暴露最小调试字段

目标：

让这轮修复变得可验证，而不是靠肉眼猜。

需要暴露：

- `final_query_type`
- `final_target_topic`
- `protected_anchor_terms`
- `rewrite_override_applied`
- `semantic_quality_flags`

阶段完成标志：

- 任何一个错 query 都能在一次响应里看出是 semantic 错、rewrite 错，还是 topic anchor 错

---

## 六、Phase 0 验收集

### 验收包 A：限定词保护

queries：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c'是什么意思`

必须满足：

1. `query_type != general_search`
2. `target_topic` 不得退化成裸缩写
3. `protected_anchor_terms` 非空
4. `must_terms` 含限定词锚点

### 验收包 B：解释型定义

queries：

- `什么是V2V`
- `V2V的定义是什么`
- `什么是控制导引电路`

必须满足：

1. 不落到 `general_search`
2. `target_topic` 不得为空、不得是 `undefined`
3. `rewrite_override_applied` 若发生，则 topic 也应被同步重建

### 验收包 C：参数值 vs 参数意义分离

queries：

- `CC阻值是多少`
- `CC阻值代表什么意思`
- `CP占空比是多少`
- `CP占空比是什么意思`

必须满足：

1. 数值型与意义型 query 不能共用完全相同的 topic anchor
2. 必须能区分“值查找”和“释义查找”

---

## 七、验收输出格式建议

Phase 0 完成后，建议每条调试输出统一按下面格式查看：

```text
query
semantic_output
rule_query_type
final_query_type
rewrite_override_applied
final_normalized_query
final_target_topic
protected_anchor_terms
must_terms
semantic_quality_flags
```

判断是否通过只看两点：

1. 最终意图是否正确
2. 最终主题是否保留了细粒度对象

---

## 八、Phase 0 不应追求的结果

下面这些在 Phase 0 做不到，属于正常现象：

1. `V2V` 问题立即答得很漂亮
2. 参数解释直接变成最终高质量答案
3. topic resolution 已经完全命中细对象

因为这些属于 Phase 1 / 2 / 3 的工作。

Phase 0 的成功标准不是“已经答对”，而是：

> 不再把问题在最上游理解错。

---

## 九、风险点

### 风险 1：过拟合解释型模板

如果规则写得太死，会导致很多真正的 general search 被硬拉成 definition。

控制方式：

- 解释型模板必须和“被解释对象”一起判断
- 只修“问法”，不硬编码具体词

### 风险 2：限定词保护过度

如果所有词都保护，会让 query 过于僵硬，影响召回扩展。

控制方式：

- 只保护结构化强锚点
- 不保护普通修辞和泛名词

### 风险 3：semantic parser 与规则长期冲突

如果 semantic parser 和规则频繁打架，系统会变得难以维护。

控制方式：

- Phase 0 结束后，要形成一套明确的 override 条件表

---

## 十、Phase 0 完成的判断标准

只要同时满足以下条件，就可以判定 Phase 0 完成：

1. 典型解释型 query 不再掉到 `general_search`
2. 细粒度限定词不再在 rewrite 中消失
3. `query_type` 和 `target_topic` 之间不再互相矛盾
4. 能通过调试字段快速解释每次 query 的最终理解结果

最终一句话总结：

> Phase 0 的目标不是把答案做漂亮，而是让系统先知道自己到底在回答什么对象。
