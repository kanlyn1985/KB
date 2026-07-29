# Core 不内置领域知识——所有领域知识通过 Domain Pack 注入

Core 代码中不允许出现任何具体领域概念（OBC、DCDC、ISO 14229、法律合同术语等）。Class 列表、属性模板、关系类型、分类关键词、唯一性规则全部定义在 Domain Pack 中。Core 只提供框架和执行引擎。

**为什么**：我们重建系统的直接原因就是旧代码把通用能力和领域知识混在一起，导致无法复用。Core 内置领域假设是滑坡——今天加一个"verified_by"关系，明天加一个"标准号解析"，很快又变成领域绑定的。

**核心约束**：
- Class 列表来自 Domain Pack，Core 不知道有哪些 Class
- 关系类型只有 `part_of` 和 `references` 是 Core 内置的（跨领域通用语义）
- Class 的 bootstrap 发现流程产生的结果落入 Domain Pack，不落入 Core
- 判定标准：一个概念如果换三个不同领域都存在且语义相同，才能考虑提升到 Core

**代价**：每个新领域需要编写 Domain Pack；冷启动需要 bootstrap 流程。
