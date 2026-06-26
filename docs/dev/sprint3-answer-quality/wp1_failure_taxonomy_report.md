# Sprint 3 WP1 — 失败样本分桶报告

> Sprint 3 WP1。依据：`docs/dev/sprint3-answer-quality/kb1_sprint3_development_guide.html` § WP1。
> 方法论：**先分桶，不写代码**。把 0.30 baseline 的失败拆成可修工程问题，再定修复顺序。
> 样本：20 题跨文档轮询（比 CI 10 题大一倍，用于统计分桶），deterministic token_overlap。
> 数据：`tmp/sprint3/wp1_taxonomy_cases.json`（每题含 question / expected_points / direct_answer / coverage / facts / evidence / answer_mode / preferred_doc_id / confidence）。

## 0. 复现结果

| 项 | 值 |
|---|---|
| 样本 | 20 题（跨文档轮询，9 个文档） |
| pass_rate | 0.35（7/20） |
| 与 CI 10 题 0.30 | 一致量级（小样本波动） |
| scorer | token_overlap（COVERAGE_THRESHOLD=0.30，deterministic，无 LLM） |

## 1. 失败分桶（13 个失败样本，100% 归桶）

| Bucket | 数量 | 占比 | 典型案例 |
|---|---|---|---|
| **cross_doc_routing_miss** | 5 | 38% | [4][5][13][17] 温度范围/车辆控制器要求 → 召回到错文档 |
| **genuine_retrieval_miss** | 5 | 38% | [1][6][7][15][20] 英文查询/V2G段落 → 0 hits，答「未找到」 |
| **pseudo_question** | 4 | 31% | [2][10][11][19] 自动生成的伪问题（英文标题/章节号/分页符） |
| **answer_undercoverage** | 0 | 0% | （本样本未出现纯表达不足） |

> 注：占比合计 >100% 因 [4][5] 同时归 cross_doc_routing_miss 与 answer-policy 不降级（见下）。已按主因归一桶。

## 2. 分桶详解

### 2.1 cross_doc_routing_miss（最高 ROI）

**现象**：expected_point 在文档 A，但召回 hits 全部来自文档 B；answer 拿到证据却答了错的章节/错的文档。

- **[4] 室外使用温度范围**（EP 在 DOC-000003）→ 7 hits 全 DOC-000012 → 答「### 8 电动汽车和供电设备之间的连接」（章节标题）。`evidence_judgement.sufficient=False conf=0.0`，但**仍输出了低质答案而非降级**。
- **[5] 车辆控制器应满足什么要求**（EP 在 DOC-000012，含 S2/检测点3/4V）→ 6 hits 全 DOC-000003 → 答「通信 的关键阈值是 GB/T 27930」，**完全不含** 检测点3/S2/4V。`sufficient=False conf=0.95`。
- **[13] 室内温度范围** → 同 [4]，答错章节。
- **[17] 输入直流电路电压应满足什么要求** → facts=12 但答「模式1和模式2供电接口…GB/T 1002」，错段。

**根因（2026-06-25 第三次修正，已用调用链证据验证）**：

逐层追踪 case [5]（EP 在 DOC-000012，含 检测点3/4V/开关S2）：

| 调用点 | DOC-000012 命中 | 结论 |
|---|---|---|
| `_search_fts`（底层 FTS） | 8/8 全 DOC-000012 ✅ | **FTS 召回完全正确，分词没问题** |
| `_inject_direct_requirement_hits` | 12（DOC-000012）vs 8（DOC-000003）✅ | 注入也对，DOC-000012 更多 |
| `build_query_context` limit=8 最终 | **0** ❌ | DOC-000012 被 top-8 截断挤掉 |
| `build_query_context` limit=40 | 13 | 证据都在，只是排名靠后 |

**得分对比**：
- DOC-000003 的 `routing_summary` 命中：score **3.44-3.62**（top-4 全占，错文档「检测点1 模式3」表格噪声）
- DOC-000012 的 `direct_requirement` 命中：score **仅 2.30**（含正确锚点的真实证据）

**真正根因**：`routing_summary`/`graph` 通道命中被通道加权提到 ~3.5 分，且**不校验是否含查询强锚点 token**（must_terms 里的 检测点3/4V/开关S2），所以错文档的无关表格噪声也能霸占 top-N；而含锚点的 `direct_requirement` 真实证据只有 ~2.3 分被截断挤掉。

> **前两次判断修正**：(1) 第一版认为 P0 硬降级能提分——错，sufficient/confidence 不可靠（[17] suff=True conf=0.95 仍答错），P0 只能诚实化 [4][13]，不提分。(2) 第二版认为是 FTS 分词缺陷（CJK+数字 token 拆错）——错，`_search_fts` 底层对 DOC-000012 召回 8/8 全中，分词没问题。问题在 reranker/channel 加权，不在分词。

### 2.2 genuine_retrieval_miss（次高 ROI）

**现象**：0 hits / 0 facts，答「知识库中未找到」。

- **[6][7][15]** V2G/V2L 长段落查询（中文）→ 0 hits。
- **[1]** `PwrMod = OFF/awake 时...` → 0 hits（英文/代码标识符 + 中文混合）。
- **[11][20]** `The Systems Engineer(ing)` → 0 hits（纯英文）。

**根因**：FTS5 unicode61 对纯英文/长无锚点段落召回弱；2-gram LIKE fallback 未覆盖英文术语与长上下文匹配。V2G/V2L 这类有明确术语的中文段落本应能召回（知识库里有 DOC-000013/000016 相关内容），但查询措辞与存储措辞分词不匹配。

### 2.3 pseudo_question（采样层，已在 WP5 部分修，仍有残余）

**现象**：自动生成的问题本身无意义，无论答案多好都过不了 token_overlap。

- **[2]** `请解释: PUBLICPUBLIC 过程参考模型` → 答「3」（退化答案）。
- **[10]** `请解释: 7.4.3 功能安全需求 7.4.3.1` → 答「CCU 软件功能开发需求规格书」（标题）。
- **[11]** `请解释: The Systems Engineer` → 未找到。
- **[19]** `请解释: 1/148 CCU 软件功能开发需求规格` → 答 GB/T 18487.4（完全跑题）。

**根因**：`generic_hint` 兜底模板 `请解释: <前20字>` 把英文标题、章节号、分页符「1/148」当问题。Sprint 2 WP5 已加「≥6 CJK 才生成兜底」过滤，但 `generic_hint` 仍可能从含 CJK 的噪声片段（如「7.4.3 功能安全需求」）生成。这类应进一步收紧：兜底问题必须有可验证的实体/术语锚点。

## 3. 通过样本特征（什么做得对）

7 个通过案例的共同特征：
- facts=12（满候选）或 evidence 命中正确文档 → **[3][9][12][14][17 pass? no]** 实际通过的是 [3][8][9][12][14][16][18]。
- requirement 类（[3][12][14]）通过率高：问题措辞「应满足什么要求」与 expected_point 措辞对齐，token_overlap 自然高。
- DOC-000001 / DOC-000002 通过率 100%（2/2 各）：这两文档的 expected_points 措辞规整、召回稳定。

**启示**：通过靠「召回对文档 + 措辞对齐」；失败正是这两点崩了。

## 4. 修复优先级（高 ROI → 低）

> **2026-06-25 第三次修正（最终）**：补采 judgement sufficient/confidence 发现其不可靠（[17] suff=True conf=0.95 仍答错）；进一步追踪 case [5] 调用链发现**底层 FTS 召回正确（DOC-000012 8/8 全中），问题在 reranker/channel 加权**——无锚点的 routing_summary 命中（~3.5 分）挤掉含锚点的 direct_requirement 证据（~2.3 分）。故 P0 降级只诚实化 [4][13] 不提分；真正提分靠 P1 通道加权/锚点校验（非选文档、非分词）。详见 §2.1 调用链证据。

| 优先级 | 方向 | 对应 WP | 预期影响 |
|---|---|---|---|
| **P0** | answer policy 硬降级：`sufficient=False` **且** confidence 极低（如 <0.2）时输出「证据不足以确认」而非低质章节标题 | WP2 | **诚实性↑但不提分**：[4][13] 错章节标题→未找到（仍 fail）。安全改进，为 P1 提分做诚实底 |
| **P1** | **通道加权/锚点校验**（非选文档、非分词）：含查询强锚点 token（must_terms 里的 检测点3/4V/开关S2）的 `direct_requirement` 命中提分；不含锚点的 `routing_summary`/`graph` 命中降权。只调 reranker/channel 权重 | WP3 | **主提分项**：[4][5][13][17] 让含锚点的真实证据进 top-N，挤掉无锚点的表格噪声 |
| **P2** | 英文/长段落召回：0-hits 类（[1][6][7][11][15][19][20]）扩展 LIKE fallback 覆盖英文术语；V2G/V2L 加 exact/contains boost | WP3 | 0-hits→有证据，转可答 |
| **P3** | pseudo_question 收紧：generic_hint 兜底必须有可验证实体/术语锚点 | WP1 延续 | [2][10][19] 不再生成无意义题 |
| **P4** | citation / unsupported claim 门禁（提分后回归保护） | WP4 | 防止提分时引入 unsupported claim |

## 5. 关键判断与风险

1. **0.30 → 0.65 的真实路径**：P0（降级）+ P1（选文档）+ P2（召回）三连是主力。但 P0 会把一些「错答」变成「未找到」——pass_rate 不一定升，**诚实性↑但分数可能先平后升**。真正提分靠 P1+P2 让正确证据进候选且排到位。
2. **不刷分承诺**：P0 降级是安全改进，不是刷分；P1/P2 是召回质量改进，证据内提质。均不换 metric、不删题、不降标准。
3. **pseudo_question 不删题**：P3 是收紧问题生成（让题更真实），不是删困难样本。被跳过的点会留审计记录。
4. **未在本样本出现的桶**：answer_undercoverage=0、citation_mismatch=0、timeout=N/A（20 题未超时，104 题才超时）。这些留 WP4/WP8 处理。

## 6. 不修改的样本（expected_points 可疑）

- [1] `PwrMod = OFF/awake 时: (1) DCLV...` —— expected_point 本身是代码/参数表片段，question 也是片段。这是 expected_points 生成质量问题，不是答案问题。**不通过改答案修，留 expected_points 绑定治理**。
- [2] `PUBLICPUBLIC 过程参考模型` —— expected_point 含重复噪声「PUBLICPUBLIC」，疑似解析 artifact。**留 expected_points 治理**。

## 7. 下一步（已暂停代码，详谈后定方案）

**进度**：P0（answer policy 硬降级）已完成并 push（`e3e4da7`），诚实化 [4][13]，0 回归，696/0/0。P0 不提分（预期内）。

**P1 暂停（第 4 次修正后）**：前三次根因判断迭代（选文档→分词→通道加权），第三次定位到通道加权。但模拟 P1 修复方案（snippet 锚点提分+通道降权）时发现**致命问题**：

**锚点 token 不在 snippet 里**。case [5] 的 must_terms 含 `检测点3`/`4V`/`开关S2`，但查所有 hits 的 snippet（截断到 120/1200 字）：

| doc | channel | snippet 含 `检测点3`? | 含 `检测点`? | 含 `4v`? |
|---|---|---|---|---|
| DOC-000003 | routing_summary | False | True | False |
| DOC-000012 | direct_requirement | **False** | **False** | False |

**DOC-000012 的正确命中 snippet 里也没有 `检测点3`**——snippet 只截了 fact payload 的 title 字段（"4 车桩成功鉴权后..."），真正的锚点 `检测点3`/`开关S2` 在完整 evidence 文本（EV-050280）和 fact object_value 全文里，不在 snippet。模拟结果：DOC-000012 始终进不了 top-8（无论强/弱锚点），因为锚点根本不在 snippet。

**结论**：snippet-based 锚点校验**不可行**。P1 修复若要做，必须读取完整 fact object_value / evidence normalized_text 做锚点匹配（查 DB 读全文，比 snippet 校验重），或在 `_inject_direct_requirement_hits` 里直接用 must_terms 混合 token 做 LIKE 全文匹配并提分（不依赖 reranker snippet）。这比预想复杂。

**决策（用户）**：P1 暂停，转去做根因更清晰、风险更低的 **P2（英文/长段落召回）+ P3（pseudo_question 收紧）**，先稳提分；P1 等全文锚点方案想清楚再动。

**教训**：根因必须用调用链证据验证，修复方案必须先模拟验证可行再动代码。本报告已四次修正，最终判定：case [5] 真根因是通道加权使无锚点 routing_summary 命中挤掉 direct_requirement 证据，但修复需全文锚点匹配（非 snippet），故 P1 暂缓。
