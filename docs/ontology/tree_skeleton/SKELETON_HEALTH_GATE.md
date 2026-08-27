# 骨架体检门（Skeleton Health Gate）v1.0

> 被测对象：`docs/ontology/tree_skeleton/skeleton_v0.6.json`（231 节点 / 243 边，7 层 R/F/L/P/G/Q/M）
> 入口命令：`python agent_kb_core/validation/run_skeleton_health.py`
> 一句话：一条命令跑两把尺（结构尺 + 内容尺），产出「骨架所有节点合起来能不能把产品做出来」的体检报告。

## 0. 独立性原则（为什么标准可信）

如果标准从骨架现状推导出来（比如「ID 前缀等于层」「R→F 关联存在」），测试就变成「骨架是否符合它自己」——
永远自圆其说，测不出真实缺口，没有测试意义。

因此两把尺的判定依据**完全不来自骨架**：

| 尺 | 尺子（依据） | 独立来源 |
|----|-------------|---------|
| 结构尺 | 本体规则 `skeleton_health_rules.json` | RFLP 本体 + 系统工程 V 模型（层间链 / 验证闭环 / 实例 / 工艺） |
| 内容尺 | 领域清单 `skeleton_coverage_map.json` | OBC/DCDC 领域知识 + 行业标准（GB/T 40432/18487、ISO 26262/14229/15118、ASPICE） |

骨架是被测对象，两把尺是固定不变的「尺子」。换任何骨架版本，尺子不变。
**耦合被隔离在显式映射层**（`skeleton_coverage_map.json` 的 `node` 字段），不在检查器代码里。

## 1. 两把尺（结构与内容分开测）

结构尺和内容尺是**两个独立维度**：结构再完整、内容空壳照样做不出产品；内容再厚、结构断了链也拼不成产品。
分开测，才能分别定位「骨架缺边」还是「节点缺内容」。

### 1.1 结构尺 —— 骨架能不能连成链

检查器 `check_skeleton_structure.py`（v0.3，数据驱动）。7 项检查全部由 `skeleton_health_rules.json` 的 `structure` 段定义：

| # | 检查项 | 配置来源 | 判定 |
|---|--------|---------|------|
| 1 | 叶子连通性（待细化 = 0） | `leaf_connectivity` | ❌ 36 待细化 |
| 2 | R→F satisfy 覆盖 | `chain_checks` | ✅ 11/11 |
| 3 | F→L realize 覆盖 | `chain_checks` | ✅ 11/11 |
| 4 | L→P allocate 覆盖 | `chain_checks` | ✅ 17/17 |
| 5 | 验证闭环（R 被 verify） | `closure_checks` | ✅ 11/11 |
| 6 | M 实例覆盖（instance-of） | `closure_checks` | ✅ 7/7 |
| 7 | P 物理件 produce 覆盖 | `produce_check` | ✅ 26/26 |

软关系/参考节点豁免、SWC 与工艺验证子节点的「懒拆」分类桶，全部读配置，不在代码里。

### 1.2 内容尺 —— 每个节点有没有落地内容

检查器 `check_skeleton_coverage.py`（v0.9 映射配套）。两档判定：

- **覆盖**：85 个工作包要素是否映射到骨架节点 → `full` / `partial` / `gap`。
- **深度**：映射节点是否有内容 → `filled` / `thin` / `empty`。
  `filled` =（unit≥10 且 doc≥5）**或**（单本权威源：unit≥30 且 doc≥1 且文档名含权威标记，如 手册/标准/IEC/SN/GB）。
  阈值与权威标记读 `skeleton_health_rules.json` 的 `content` 段，可配。

## 2. 四件套文件（参数化后的可复用框架）

| 角色 | 文件 | 说明 |
|------|------|------|
| 被测对象 | `skeleton_v0.6.json` | 231 节点 / 243 边（satisfy 31 · realize 29 · allocate 57 · verify 66 · produce 46 · instance-of 8 · issue-on 6） |
| 尺子①结构规则 | `skeleton_health_rules.json` | 层名 / 边类型 / 豁免前缀 / 分类桶 / 检查项 / 阈值 |
| 尺子②领域清单 | `skeleton_coverage_map.json` | 85 要素 → 节点（人工显式映射，独立于骨架） |
| 落地数据 | `llm_landing/node_cards.jsonl` | 按节点聚合的文档/单元（`build_node_cards.py` 产出） |

检查器里**没有一行领域硬编码**；换产品只改规则 + 清单，代码零改动。

## 3. 使用

```bash
python agent_kb_core/validation/run_skeleton_health.py          # 体检报告（人类可读）
python agent_kb_core/validation/run_skeleton_health.py --json   # 机器可读（供门禁）

python agent_kb_core/validation/check_skeleton_structure.py     # 只看结构尺
python agent_kb_core/validation/check_skeleton_coverage.py      # 只看内容尺
```

退出码：`0` = 结构全通且无空壳；`1` = 有待办（落地/细化，非结构缺失）。

## 4. 当前基线（2026-08-26）

```
[结构尺] 7/7 通过
[内容尺] 覆盖 85/85 = 100.0% · 深度 filled 85 / thin 0 / empty 0
结论: PASS —— 结构全通 + 内容全落地（首次诚实满绿）
```

达成路径：
- oracle 扩展（mapping v0.8→v0.9，81→85）：FUSA 7 条从父节点细分到 G-FUSA-ITEM/HARA/FSC/TSC/HWMETRIC/VAL/CASE，
  新增 TE-SW/TE-IF/TE-STD → G-VERIFY-SW/IF/STD，SYS-DCDC → F-DCDC。
- 内容落地：ISO 26262 条款级（-3 第4-7章 / -4 第6-8章 / -5 第8-10章 / -6 第9-11章 / -8 第9-10章 / -2 第6章）
  + MCU_SBC 安全机制矩阵 + GBT 34658 一致性测试 + DBC 接口 + GBT 24347/18487 型式试验 + 系统部知识库
  （Feature 规范/培训课件/需求模板，corpus/SYS/）。
- 此前 v1.1 基线里的空壳（G-METHOD-WCCA/G-VERIFY-PERF/Q-MSA）与 thin（Q-DQA/Q-SPC/Q-8D/F-DCDC）
  均已在前几轮补齐；本轮清零的是新入尺的 11 个节点。

## 5. 已验证的性质（gate 的双向灵敏）

| 性质 | 验证方式 | 结果 |
|------|---------|------|
| 正向灵敏 | landing → empty→filled | ✅ |
| 反向灵敏（回归） | 删内容 → filled→empty，幅度正确 | ✅ |
| 无副作用 | 重落地搬内容，旧节点 0 降级 | ✅ |
| 配置灵敏 | 改阈值不改代码，结果跟着变 | ✅ |

## 6. 复用指南（换产品）

三步，检查器代码零改动：

1. **换骨架**：新产品的 `skeleton_vX.json`（RFLP 七层 + 7 类边）；
2. **换规则**：按新产品的层/边/节点前缀改 `skeleton_health_rules.json`；
3. **换清单**：写新产品的 `skeleton_coverage_map.json`（工作包 → 节点）。

就位后 `run_skeleton_health.py` 直接跑出新产品的体检报告。

> 边界：RFLP 本体对「物理硬件产品」直接复用；纯软件/纯服务「物理层」不成立，本体需替换，
> 只剩「两把尺 + 独立性」方法论通用。

## 7. 版本历史

- v0.1–v0.3：曾把骨架现状当标准（自证循环），已废弃。
- v0.4：三条独立公理 + 86 要素 + `check_product_completeness.py`（见 `product_completeness_standard.md`，已废弃）。
- v1.0：重构为「两把尺 + 体检门」，规则/清单/阈值全部参数化，可复用框架。
- v1.1（本版）：深度判定加「单本权威源也算 filled」；落地 IEC62380/SN29500 → RELPREDICT filled。