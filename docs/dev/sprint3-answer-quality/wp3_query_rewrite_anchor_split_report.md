# WP3: query_rewrite 锚点拆分（整句 must_term → should_terms 锚点）

> Sprint 3 WP3 子任务。承接 WP1 taxonomy 诊断突破（5/6 降级 case 根因是 query_rewrite 整句
> must_term + should_terms 空）。
> 日期：2026-06-26
> 关联：WP1 taxonomy 第 5 次根因修正、WP2 [6] 元数据降权

## 1. 诊断突破

WP1 taxonomy 发现 6 个降级 case（[1][2][4][7][12][19]）的 raw FTS 都返回了正确文档的
hits（13-66 个），但 ctx hits 里正确文档被截断/选错排除了。深入 query_rewrite 发现 **5/6 降级
case 把整句作为一个 must_term，should_terms 为空**：

| Case | must_terms | should_terms |
|---|---|---|
| [4] | ['室外使用的供电设备正常工作的温度范围'] | [] |
| [12] | ['室内使用的供电设备正常工作的温度范围'] | [] |
| [19] | ['室内设备在最高温度为+40℃时，其相对湿度'] | [] |
| [1] | ['OFF/','DCLV'] | [] |
| [2] | ['VAL'] | [] |

**根因链**：
1. 整句 must_term → FTS 通用匹配返回 100+ hits（任何含"温度""范围"的段落）
2. should_terms 空 → reranker 无锚点区分相关/不相关（_lexical_score 无 should_term 加分）
3. _structured_search_seeds 和 _direct_fact_hits 用 should_terms 作 FTS 种子，空则少召回
4. 正确证据被通用匹配淹没，挤出 top-N → 降级

对比通过 case（[3] should=['OBC','on-board charger']、[13] must_n=10）有结构化锚点。

## 2. 改动

`query_rewrite.py`：
- 新增 `_split_long_cjk_sentence_to_anchors(text)`：对长无空格 CJK 句子（>=8 CJK 字符），
  提取已知领域复合词（温度范围/供电设备/室外使用/正常工作/相对湿度/最高温度 等 19 个）+
  单领域关键词（温度/湿度/范围/室外/室内/供电/充电/放电/蓄电池 等 20 个）作为 2-6 字锚点。
  短查询和 Latin 查询不受影响。
- `_should_terms`：当结果为空（整句 must_term 无 aliases）时，对每个 must_term 调用拆分，
  把锚点填入 should_terms。只在新触发路径生效，已有 should_terms 的查询不变。

不改 query_api 主链路结构，只在 query_rewrite 的 should_terms 生成加一条增量规则。

## 3. 验证

### 3.1 锚点生成（improved recall signal）

| Case | 拆分前 should_terms | 拆分后 should_terms |
|---|---|---|
| [4] | [] | ['温度范围','供电设备','室外使用','正常工作','温度','范围'] |
| [12] | [] | ['温度范围','供电设备','室内使用','正常工作','温度','范围'] |
| [19] | [] | ['相对湿度','最高温度','温度','湿度','室内'] |

### 3.2 召回改善（[4][12] 正确文档进入候选）

| Case | 拆分前 ctx exp_doc hits | 拆分后 ctx exp_doc hits |
|---|---|---|
| [4] | 0 | 1（DOC-000003 进入候选） |
| [12] | 0 | 1（DOC-000003 进入候选） |
| [19] | 0 | 0（未改善） |

正确文档从"完全没进候选"变成"进入候选"——召回层面的真实改善。

### 3.3 pass_rate（无变化，无回归）

| | 拆分前 | 拆分后 |
|---|---|---|
| 20q pass_rate | 0.35（7/20） | 0.35（7/20） |
| 逐案状态 | — | 全部 20 case pass/fail 完全一致（0 回归） |

pass_rate 无变化：[4][12] 正确文档进入候选但只有 1 个证据 hit + evidence_judgement 判
insufficient → 仍降级。召回改善尚未转化为 pass，需要更多正确证据召回 + judgement 改善。

### 3.4 测试

- fast suite：711 passed / 0 failed / 0 xfail（无回归）
- definition/CP query 无回归（已有 should_terms 不触发拆分）

## 4. 诚实披露

1. **召回改善但 pass_rate 无变化**：锚点拆分让 [4][12] 正确文档进入候选（从 0 hit），是
   真实召回改善，但不足以 pass（证据 judged 不足）。这是中性的质量改善（召回更准）。
2. **[19] 未改善**：锚点"相对湿度/最高温度"召回的还是错文档（DOC-000015），需进一步排查。
3. **下游瓶颈**：正确文档进入候选后，pass 还需 (a) 更多正确证据召回（当前只 1 hit），
   (b) evidence_judgement 对"温度范围"类查询的 sufficiency 判定改善。

## 5. 边界合规

- ✅ 不重写 query_api/answer_api 主链路（只改 query_rewrite should_terms 生成增量规则）
- ✅ 不删 expected_points 数据
- ✅ answer_changed_by_ontology 仍 false
- ✅ 改进/回归案例均已记录（[4][12] improved recall, 0 regressions）

## 6. 后续

- [4][12] 下游转化：更多正确证据召回 + judgement sufficiency 改善。
- [19] 排查为何锚点未召回 DOC-000003。
- 真实 retrieval miss [11][20]（DOC-000005）需 WP3 召回增强（本任务锚点拆分未覆盖）。
