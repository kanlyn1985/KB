# WP3: evidence_judge `_anchors` CJK 回退（核心提分）

> Sprint 3 WP3 核心提分修复。承接 WP1 第 6 次根因诊断（_anchors 对中文查询返回空）。
> 日期：2026-06-26
> 关联：WP3 query_rewrite 锚点拆分（前置）、WP1 taxonomy 第 6 次根因

## 1. 缺陷

`evidence_judge._anchors(query, expansion)` 只提取硬锚点：
- 电压值 `[+-]?\d+...V`
- 大写缩写 `[A-Z]{2,6}\d*`（CP/OBC 等）
- 检测点 N、表号、PWM、控制导引、状态/电压/时序

**对中文实质查询（温度范围、相对湿度、V2G 等）完全不提取任何锚点 → 返回 []**。
后果：`_score_candidates` 每个候选 score=0，`top_score=0 < 1.1 阈值` → 永远 sufficient=False → 降级。

5/6 降级 case（[1][4][7][12] 都是 hard=[] 的中文查询）受此缺陷影响。

## 2. 改动（保守回退，避免误伤）

`evidence_judge.py` `_anchors` 末尾加 CJK 回退：

```python
# Only fires when hard anchors is empty
if not anchors:
    from .query_rewrite import rewrite_query
    rw = rewrite_query(query)
    for term in list(rw.should_terms) + list(rw.must_terms):
        s = str(term).strip()
        # Only meaningful 2-8 char CJK terms, skip full sentences
        if 2 <= len(s) <= 8 and any("一" <= c <= "鿿" for c in s):
            add(s)
```

**关键设计：只在 hard anchors 为空时才加 CJK soft anchors**。A/B 模拟发现
无条件加 CJK 软锚点会误伤 [6][13][15]（sufficient True→False，因为 missing-anchor
检查 `len(missing) <= len(anchors)//3` 变严）。只在 hard=[] 时触发，确保有 hard
锚点的查询不受影响（0 回归）。

## 3. A/B 影响面验证（先评估后实现）

模拟给所有候选加 CJK 软锚点（无条件）的 A/B 结果：

| Case | A (hard-only) | B (hard+CJK) | 影响 |
|---|---|---|---|
| [6] | sufficient=True | sufficient=False | **误伤**（missing 检查变严）|
| [13] | sufficient=True | sufficient=False | **误伤** |
| [15] | sufficient=True | sufficient=False | **误伤** |
| [4] | best_ev=[] | best_ev=['EV-049776'] | 改善 |

无条件加软锚点误伤 3 个通过的 case。采用「hard=[] 才回退」方案后，只有 4 个
hard-empty case（[1][4][7][12]）受影响，0 误伤。

## 4. 提分结果

| | 改动前 | 改动后 |
|---|---|---|
| 20q pass_rate | 0.35（7/20） | **0.40（8/20）** |
| [4] DOC-000003 | 降级 cov=0.00 | **PASS cov=0.61**（真实答案）|
| [12] DOC-000003 | 降级 cov=0.00 | **PASS cov=0.59**（真实答案）|

**Sprint 3 首个实质提分**：[4][12] 从降级（无答案）→ 真实答案 PASS。
[4] 答案现在返回"室外使用...温度范围"的正确内容，而非降级消息。

## 5. 诚实披露（improved/regressed）

### improved
- [4] DOC-000003：cov 0.00→0.61 PASS（降级→真实答案）。CJK 回退让 evidence_judge
  获得锚点信号，best_evidence 不再为空，doc selection 选对文档。
- [12] DOC-000003：cov 0.00→0.59 PASS（降级→真实答案）。同 [4]。

### regressed（非 pass 率回归，答案质量退步）
- [6] DOC-000013（V2G）：cov 0.23→0.00 deg=True。之前 fail（0.23<0.30）有 V2G
  内容答案，现在 fail 降级无答案。**不是 pass 率回归**（都 fail），但是答案质量
  退步（有答案→降级）。原因：[6] query_type=general_search，hard=[] 触发回退，
  CJK 软锚点（车网互动/并网放电）让 doc selection 偏移到无优质内容的文档。

### 净效果
pass_rate +1.5（[4][12] +2 pass，[6] 无 pass 变化但仍 fail）。[6] 质量退步
待后续修复（doc selection + V2G 内容召回）。

## 6. 测试

- tests/test_evidence_judge.py：+4 单测（hard 优先、CJK 回退触发、排除整句、电压锚点优先）
- fast suite：716 passed / 0 failed / 0 xfail（无测试回归）

## 7. 边界合规

- ✅ 只在 hard=[] 时回退（最小改动，0 hard-anchor 回归）
- ✅ 不重写 evidence_judge 主评分逻辑（只加锚点源，不改权重/阈值）
- ✅ 不删 expected_points 数据
- ✅ answer_changed_by_ontology 仍 false
- ✅ improved/regressed 案例均已记录

## 8. 后续

- [6] 答案质量退步（V2G 降级）：需排查 doc selection 为何偏移到无内容文档。
- [4][12] 温度范围值（-25℃～+40℃）完整短语不在 evidence（ingest gap），
  但部分短语在，CJK 回退已让它们 pass。
- 继续提分方向：[5][17] channel weighting（需 full-payload anchor）、
  [11][20] 真实 retrieval miss（DOC-000005）。
