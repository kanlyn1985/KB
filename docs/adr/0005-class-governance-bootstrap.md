# Class 定义由 Domain Pack 提供，经 bootstrap 发现后人工锁定

Class 不由 Core 内置，也不由 LLM 自主创造。流程是：从代表性文档中 bootstrap 发现候选 Class → 人工 review 合并同义 Class → 锁定写入 Domain Pack → 后续萃取按已确认 Class 工作。遇到无法归入现有 Class 的实体标记"待分类"，不自动新建。

**为什么**：三种路线各有致命问题——
- Core 内置 Class（如固定提供 Parameter/Standard/Method）：违反领域中立原则
- LLM 自主创造 Class：Class 名不稳定（同一概念在不同文档里被叫 Parameter/Spec/Metric），骨架漂移导致查询不可靠
- 纯人工预定义：面对上千篇文档无法穷举所有 Class

bootstrap + 人工锁定的组合解决了这些问题：LLM 负责发现候选（覆盖面），人工负责治理（稳定性）。Class 一旦锁定就是契约，保证查询可靠性。

**核心原则**：Class 是契约，一旦确认就锁定。新增 Class 是人工决策，不是 LLM 自主行为。萃取过程中 LLM 只能将实体归入已有 Class，不能创造新 Class。
