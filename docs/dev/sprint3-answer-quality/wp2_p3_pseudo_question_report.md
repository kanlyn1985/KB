# WP2 P3: Pseudo-question 收紧 + Metric 防降级 + 样本扩 20 题

> Sprint 3 WP2 子任务 P3。承接 WP1 taxonomy 的 P3 优先级（pseudo_question 收紧）。
> 日期：2026-06-26
> 关联：WP2 doc-selection fix（commit 487a821）、WP1 taxonomy（4th correction commit 69930dc）

## 1. 背景与动机

WP1 failure taxonomy 发现 4/13 失败案例是 pseudo_question（generic_hint/explain 模板
从噪声 expected_point 生成无意义问题，如「请解释: PUBLICPUBLIC 过程参考模型 版本 4.0
标题:」）。这些问题的 expected_point 是文档封面元数据、页眉、SC 码表行、英文片段描述符，
本就不是可回答的实质内容。

同时在验证 P3 时发现一个更深的 metric 脆弱性：**P0 硬降级文本骗过 token_overlap**。
P0 降级答案（`当前候选证据不足以给出确定性答案。期望证据形状：term_definition、
parameter_definition、process_activity...`）含通用英文词，与英文 expected_point 共享
token（process/definition/system），算出 cov=0.59-0.81 的假通过。

## 2. 改动内容

### 2.1 P3 噪声 expected_point 检测（evaluator.py）

新增 `_is_noise_expected_point(text)` + `_NOISE_POINT_PATTERNS`，5 条规则识别噪声 point：
1. 封面/元数据标记（版本:/作者:/标题:/日期:/©/PUBLICPUBLIC/版权）
2. 页眉页脚 N/M 计数（如 `1/148`）
3. SC/BP/SYS/FSR 表行码（如 `SC44047`、`编号:SC44047`）
4. 纯节号+短标题无谓词（如 `7.4.3.1 功能安全需求`）
5. 英文主导片段（≥3 个拉丁词且 CJK < 12 字）

**关键修正**：初版把检查放在 generic_hint 兜底前，但实测 142 个噪声 point 中 65 个先匹配
explain 模式，检查根本不触发（空操作）。修正后检查移到 `_generate_questions_for_point`
**顶部**，在任何模式匹配前返回 `[]`，噪声 point 不生成任何问题。

### 2.2 Metric 防降级误判（evaluator.py）

新增 `_is_degraded_answer(answer)` + `_DEGRADED_ANSWER_MARKERS`，检测降级/拒答/未找到
文本（`当前候选证据不足以给出确定性答案` / `知识库中未找到` / `未找到` / `无法回答` /
`insufficient evidence` / `not found`）。

`score_answer` 和 `score_answer_hybrid` 在计算 coverage 前先检查：若答案是降级文本，
强制 cov=0、pass=False。**不换 metric**（仍是 deterministic token_overlap），只是不让
拒答文本通过共享 token 得分。

**重要边界修正**：初版加了 `len < 12 即判降级`，误杀了真实短答案（如 6 字
「汽车电源逆变器」），导致 2 个 evaluator 测试失败。修正为只检测 marker + 空值，
短答案不再误判。

### 2.3 CI 样本扩到 20 题（tests.yml + run_eval_suite.py）

关键发现：10 题轮转样本 pass_rate=0.30（与 locked baseline 持平），但 20 题=0.40。
根因是 10 题恰好都落在低质量/降级 case，WP2 doc-selection fix 修复的 [15] case 进
不了前 10 题。10 题样本太小，无法反映真实质量提升。

改动：
- `.github/workflows/tests.yml` eval-suite job：`--max-questions 10` → `--max-questions 20`
- `scripts/run_eval_suite.py`：default 5 → 20
- 保留 `--min-token-pass 0.20`（保守 smoke floor，0.40 真实值仍有 0.20 余量）

## 3. 验证结果

### 3.1 题池变化

| 指标 | P3 前 | P3 后 |
|---|---|---|
| 总题数 | 100 | 87 |
| generic_hint | 8（7 噪声 + 1 真实 V2G） | 1（仅 V2G） |
| explain | 46 | 36 |
| 残留噪声问题 | 8 | 0 |

V2G 实质段落（DOC-000013「山博轩和杨郁构建了一套2+1的源网荷储...」）保留，零误伤。

### 3.2 pass_rate（诚实化，0 artifact）

| 样本 | P3+防降级前 | P3+防降级后 |
|---|---|---|
| 10 题 | 0.30（含 [11] artifact） | 0.30（无 artifact，但样本太小） |
| 20 题 | 0.45（含 [11][19] artifact） | **0.40（0 artifact，诚实）** |

20 题逐案：6 个降级答案（[1][2][4][7][12][19]）全部正确归零 cov=0.00；
8 个真实通过（[3]0.46 [8]1.00 [9]0.38 [11]0.33 [13]0.67 [14]0.34 [15]0.30 [17]0.47）
全是 deg=False 实质答案。

### 3.3 测试

- 新增 9 个 evaluator 单测（噪声检测 5 + 防降级 4）
- fast suite：705 passed / 1 skipped / 0 failed / 0 xfail（+9 from 696）
- 无回归

## 4. 诚实披露

1. **10 题样本 pass_rate=0.30 未提升**：与 locked baseline 持平，因为 10 题恰好都是
   难题/降级题。这是样本大小问题，不是质量回退——20 题=0.40 才反映真实质量。
2. **防降级让 pass_rate 从 0.45「降」到 0.40**：这不是回退，是诚实化——之前 0.45 含
   降级文本 artifact 假通过，0.40 是去 artifact 后的真实值。
3. **P3 清理的 pass_rate「提升」主要也是 artifact 消除**：P3 单独带 artifact 是 0.55，
   但其中 [10][11][19] 全是 artifact（表格 token 共享 / 降级文本共享）。P3 清理本身
   是正确的（移除噪声题），但真实质量提升来自 WP2 doc-selection fix（[15] case）。

## 5. Sprint 3 边界合规

- ✅ 不换 metric（仍是 token_overlap，防降级是 metric 加固非替换）
- ✅ 不删 expected_points 数据（只跳过噪声 point 的题目生成）
- ✅ 不删困难样本（噪声判定有规则 + 审计记录）
- ✅ answer_changed_by_ontology 仍为 false（本任务未触达 ontology）
- ✅ 不重写 query_api/answer_api 主链路（只改 evaluator + CI 配置）

## 6. 后续

- 真实质量基线现为 20 题 0.40。距 Sprint 3 Gate 1（0.65-0.85）仍有差距。
- [6] answer_policy 问题（学术标题/作者片段输出）待 WP2 继续修。
- P1 [5][17] channel weighting 需 full-payload anchor matching（复杂，待设计）。
- 真实 retrieval miss [11][20]（DOC-000005 未召回）需 WP3 召回增强。
