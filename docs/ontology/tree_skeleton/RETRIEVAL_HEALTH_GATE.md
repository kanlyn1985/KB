# 检索体检门（Retrieval Health Gate）v1.1

> 被测对象：节点卡检索表面（`llm_landing/node_cards.jsonl`）+ `understand_query`/`retrieve` 管线
> 入口命令：`python agent_kb_core/validation/run_retrieval_health.py`
> 一句话：golden case 不再是散落的样例，而是「什么必须测 + 及格线多少」的完整标准。

## 0. 为什么 golden case 本身不是标准

30 个手写 case 只能覆盖 41/231 节点（17.7%），P 层只有 6%、G 层 15%。case 是**数据**，
标准是**尺子**——它回答两个独立问题：

1. **充分性**：什么必须被测到？（由 oracle 定义，不是拍脑袋写 case）
2. **质量**：测出来要及格到什么线？（阈值，写在规则文件里）

本门沿用骨架体检门的独立性原则：充分性尺的依据是 `skeleton_coverage_map.json`（oracle 85 要素），
与骨架、与 case 集合本身都独立；case 只是把 oracle 的「每个工作包」翻译成「一个可检索的问题」。

## 1. 两把尺

| 尺 | 依据 | 判什么 |
|----|------|--------|
| 充分性尺 | `retrieval_case_rules.json` + oracle 85 要素 | 每个 oracle 要素 ≥1 case 打到其映射节点；每个骨架节点 ≥1 case；分层地板 80%；负例 ≥5 |
| 质量尺 | 同一规则文件的阈值 | 正例 Hit@5 ≥90% 且 MRR ≥0.60；负例 top1 分 <0.35（假召回检测） |

## 2. 判定语义（关键，不是放水）

- **层级命中**：查询「OBC 主功率拓扑」命中子节点 `P-HW-OBC-PFC` 也算命中父概念 `P-HW-OBC`
  （打到更细的块 = 找到了这个功能域，检索语义上等价）。
- **多答案**：允许 case 声明多个等价正确节点（如「单元验证怎么做」→ G-PROC-STD 或 G-VERIFY-SW 都对）。
- **子卡归一**：`#n` 分块卡归一到父卡，不因分块机制误判。

## 3. 四件套文件

| 角色 | 文件 |
|------|------|
| 尺子（规则） | `retrieval_case_rules.json` |
| 正例数据 | `llm_landing/golden_cases.json`（234 条：oracle 要素 + 全节点 + 多答案） |
| 负例数据 | `llm_landing/negative_cases.json`（6 条语料外查询） |
| 门脚本 | `agent_kb_core/validation/run_retrieval_health.py` |

## 4. 当前基线（2026-08-26）

```
[充分性尺] oracle 要素 85/85 有 case · 节点 231/231 有 case · 分层 7/7=100% · 负例 6>=5
[质量尺] Hit@5: 234/234 = 100.0% · MRR: 0.848 · 负例 top1 最高分 0.314 < 0.35
结论: PASS
```

## 5. 残余清零（曾 1 个，已解决）

`F-DCDC-PROTECT`（DCDC 保护功能）曾被 `F-OBC-PROTECT`（101 单元/51 文档）内容量压制，
是检索门捞出的**跨层盲点**——oracle 85 只映射到父节点 `F-DCDC`，内容尺漏掉了它。
这正是「完整标准」的价值：结构/内容/检索三层互相补盲。两处修复：

1. 落地 GBT 24347-2021 保护功能条款（4.3 保护功能 / 5.4 保护功能试验）→ 16 单元/6 文档；
2. 节点名补保护范围「DCDC 保护功能（过压/欠压/过流/短路/过温）」，并修
   `_expand_alias_parts` 保留整词短语（「DCDC 保护功能」不再被拆成「DCDC」/「保护功能」泛词）。

Hit@5 从 99.6% → 100%。

## 6. 生产索引（导入 + 端到端）

节点卡 → SQLite 生产索引（`node-index.sqlite3`）：239 对象 / 1356 卡 / 434 事实 / 29528 证据，
导入约 70s（含 trigram FTS 批量重建 + HashEmbedding 向量索引，各 31557 条）。

端到端命中验证：HARA→G-FUSA-HARA、PMHF→G-FUSA-HWMETRIC、8D→Q-8D、CAN 矩阵→R-IF、
DCDC 保护功能→F-DCDC-PROTECT。生产查询同时走 `lexical_search`（trigram FTS）+ `vector_search` 两通道。

> FTS5 分词器已从 unicode61 换为 **trigram**（SQLite 内置，支持中文 ≥3 字符子串匹配；
> ICU 未编译、jieba 需额外 C 扩展，均不可用）。trigram 对 <3 字符短词不匹配，已用 LIKE 兜底补齐。
>
> 向量索引已启用（HashEmbeddingProvider 256 维）。注意：HashEmbedding 仍是**契约验证基线**
> （确定性哈希，非语义模型）；生产级语义检索需换 RemoteJSONEmbeddingProvider（外部嵌入）。

## 7. 图通道（2026-08-27 启用）

骨架 `skeleton_v0.6.json` 的 243 条本体关系（allocate/satisfy/realize/verify/produce/instance-of/issue-on）
此前只存在于骨架 JSON，`import-node-cards` 不写 `graph_edges`，生产查询的图通道（BFS，生产权重 0.85）一直空转。

修复（`import_node_cards.py`）：

1. 读入骨架 `relations` → `ObjectRelation`（证据映射边，conf 0.75/0.95，status=materialized）；
2. 补结构树 `contains` 边（parent→child，224 条，conf 0.9）——跨层主链边覆盖不到
   G 过程层 / P-KNOW 知识节点的邻域，无结构树时这些起点 BFS 度数为 0；
3. 合计 **467 条边**随导入写入 `graph_edges`（存量库已就地补齐，向量未重算）。

验证：`HARA分析怎么做` → graph_search 贡献 8 候选，Top-5 出现纯图通道的兄弟方法群 `G-FUSA`；
`输出纹波要求是多少` → 2 跳内跨层命中 R-PERF/R-PROTECT/P-HW-OBC-PFC。健康门禁 PASS 无回归
（Hit@5 100%，MRR 0.848）。
## 8. 挑选层修复（2026-08-27，P1+P2）

多通道召回后挑选层的两处失衡（评审结论见会话记录）：

### P1：多样性封顶覆盖持久池

内存 fuse 的 `MAX_PER_OBJECT=2` 只作用于基线候选；持久池（词法/向量/图）合并在其后，
同节点影子事实曾借此占满 Top-12 尾部（实测 `fact:node:P-HW-OBC` 与其 table_row 双双入围）。
修复：`hybrid_retrieve` 重排后按父对象重申封顶（`_enforce_diversity`）；
ContextPack 卡槽选择统一走 `select_retrieval_cards()`（排名序 + 对象兜底取聚合父卡 + 同对象封顶）。

### P2：形态补槽 + 假充分守门

意图要求的证据形态（procedure/table_row 等）此前只做事后判定、不参与事前选择——
库里存在对应类型时也可能因原始分低进不了前 K。修复分两层：

- **补槽**：判定器公开 `required_shape_groups()`，`fill_missing_shapes()` 用同一张映射
  在选择阶段按缺失形态从全量事实面补捞（绑定证据、≤4 条/每节点限 2/需强相关）；
- **守门**：非主体命中的形态类事实（图邻域影子事实等）必须过相关性门槛
  （整短语包含或 ≥2 个词元命中，中文按 bigram 切分）才能借"对象兜底/类型兜底"进入——
  否则「标定怎么做」会被 G-VERIFY（振动测试）的 procedure 影子事实抬成假 sufficient(0.85)。
  实测该查询在真实语料（81 条 procedure 零命中"标定"）下正确回到 partial(0.40)：
  这类 partial 是**语料空洞**的诚实信号（标定/采样/AuxPower 的过程内容待落地语料），不是排序缺陷。

回归：59 单测全过（新增 `test_context_selection.py` 9 条钉死行为契约）；修复
`negative_cases.json` 丢失的 `kind` 字段（08-25 重写遗留，曾使套件负例断言空转）；
健康门禁 PASS 无回归。真实管线验证：HARA/OBC 原理/热仿真保持 sufficient，
标定/AuxPower 保持诚实 partial。

> 已知既有限制（本次未动）：`required slots` 未解析的查询被判定器硬性封顶 0.74 →
> 「输出纹波要求是多少」恒为 partial(0.74)，属槽位机制的既有行为。
## 9. P3 通道消融与分数尺度实验（2026-08-27）

**动机**：跨适配器直接合并原始分数，词法（可达 3~4 分）系统性压制余弦(≤0.95)/图(≤1)，
通道话语权失衡疑虑（评审 P3）。

### 消融基线（43 条分层样本，离线 hash 向量通道）

| 变体 | Hit@5 | MRR |
|---|---|---|
| lexical_only | 74.4% | 0.3764 |
| vector_only(hash占位) | 39.5% | 0.2659 |
| graph_only | 74.4% | **0.3926** |
| lexical+vector | 74.4% | 0.3636 |
| **full_three(raw 现状)** | 72.1% | 0.2988 |

三通道全开低于词法单开 —— 尺度混合确有代价；同时 graph_only MRR 最高
（目标对象兜底 + 邻域兄弟命中），图通道价值被证实。

### 自归一实验（self_max：各通道除以自身 Top1 ×2.0）

| 变体 | Hit@5 | MRR |
|---|---|---|
| full_raw | **72.1%** | **0.2988** |
| full_selfmax | 46.5% ↓↓ | 0.2372 |

分意图 MRR：procedure 0.148→0.033、test_method 0.223→0.087、constraint_lookup 0.293→0.192
全大幅回退；仅 definition(0.08→0.17)/general_search(0.625→0.642) 微升。

### 结论（数据否决 naive 归一）

1. 各通道**精度极不均衡**时（hash 占位通道只有 39.5%），原始分数的"尺度压制"
   实际是免疫系统——把弱通道压在强通道之下；self_max 把弱通道 Top1 强拉到与
   强通道平权，等于放大噪声。
2. **保持 raw 合并为默认**；`ProductionCandidateProvider(normalize=...)` 开关保留，
   `channel_normalize` 已透传至 `query_production_store`。
3. 重跑协议固化：`validation/channel_ablation_*.json` 存有全部逐 case 明细；
   接入真实语义向量（bge-small-zh）后应重跑本消融再做归一/RRF 决策——届时若
   向量通道精度接近词法，尺度问题才真正需要修，且可考虑按实测精度调权的
   加权 RRF 替代方案。