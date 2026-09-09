# Golden Cases 扩充结果（2026-08-18）

## 覆盖扩充

从 15 个 → **30 个** golden cases，补齐 F/M/Q/L/R 各层缺口：

| 层 | 扩充前 | 扩充后 | 新增示例 |
|---|---|---|---|
| F（功能） | 0 | 7 | 充电功能/V2L放电/CP控制导引/保护功能/DCDC转换 |
| M（实例） | 0 | 2 | G5平台/曼岛项目 |
| Q（质量经验） | 0 | 4 | 经验教训/失效分析/客诉处理 |
| L（逻辑） | 2 | 5 | 功率控制环路/启动预充/峰值功率 |
| R（需求） | 5 | 8 | EMC要求/环境可靠性 |
| G（过程） | 13 | 13 | — |
| P（物理） | 5 | 5 | — |

## 评测结果（正式管线 query-production）

- **Hit@10 = 100%（30/30）**
- **sufficient 判定 = 21/30**（知识/原理/安全/功能类；参数/方法类为 partial 属正常保守）

## 修复的问题（扩充过程中发现）

1. **F-DCDC-CONV 别名"电压转换/低压输出"无法匹配"电压转换"**：
   `_link_target_objects` 只做整串子串匹配，斜杠分隔词不拆。
   → 修复：别名匹配时展开斜杠/顿号分隔词（"电压转换/低压输出"→"电压转换"）。
2. **R-EMC 别名"EMC 需求"无法匹配"EMC要求"**：补别名"EMC/EMC要求/电磁兼容"。
3. **M-G5 别名缺"G5"**：sync 脚本把"G5"当层级前缀 G 剥掉 → 补"G5/G5平台"。
4. **F-DCDC-CONV 的"低压输出"泛词污染 subject 判定**：移除（保留斜杠整串+DCDC转换）。

## 评测口径

命中判定：候选的 card/fact/object 任一形式命中期望节点即算 hit
（fact:node:M-G5 命中也算，因为 fact 是节点的证据事实）。

## 文件

- `docs/ontology/tree_skeleton/llm_landing/golden_cases.json`（30 个 case）
- `src/agent_kb/query/understanding.py`（别名斜杠展开）
- `domains/obc_dcdc/terminology.json`（R-EMC/M-G5 别名补充）
