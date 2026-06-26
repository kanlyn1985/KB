# WP2 [6]: Answer 学术元数据降权

> Sprint 3 WP2 子任务 [6]（answer_policy：V2G 查询输出学术标题/作者片段而非干净内容）。
> 日期：2026-06-26
> 关联：WP1 taxonomy case [6]（DOC-000013 V2G，cov=0.026 not-found）、WP2 doc-selection fix

## 1. 根因

WP2 doc-selection fix（commit 487a821）让 [6] 从 not-found 恢复为有答案（cov 0.026→0.154），
但答案质量差：输出「山博轩，杨郁 DOI: 10.12677/sg.2024.142002...comprehensive energy systems...
Keywords V2G」——这是论文首页的**学术元数据**（作者+DOI+英文摘要+关键词），不是 V2G 实质内容。

根因在 `_rank_evidence`（answer_evidence_selection.py）：general_search 分支没有学术元数据
降权。DOC-000013 的前 2 条证据都是元数据：
- EV-049930「Smart Grid 智能电网, 2024, 14(2), 11-20 Published Online...」（期刊信息）
- EV-049931「山博轩，杨郁 DOI: 10.12677/sg.2024.142002...comprehensive energy systems...
  Keywords V2G」（作者+DOI+摘要）

两者 confidence 都是 0.95，无惩罚，胜出成为 `ctx.evidence[0]`，答案直接输出其 snippet。

这些元数据块在 ingest 阶段没被 `_is_academic_header_noise` 过滤，因为它们混排 CJK（作者名、
期刊名）+ 长 English（abstract），超过了 `len<200 AND cn<10` 的阈值——filter 只抓短 header 行。

## 2. 改动

`answer_evidence_selection.py`：
- 新增 `_is_academic_metadata_evidence(text)`：检测 DOI/Keywords/Published Online/期刊引用行
  （`CJK, 2024, 14(2), 11-20` 格式）/作者署名+长英文摘要（cn<20 且 latin_words>=8 且 len>100）。
- `_rank_evidence.score` 中跨所有 intent 加 `if _is_academic_metadata_evidence(text): bonus -= 2.5`，
  让元数据证据降到实质内容之下。与现有 `if "目 次" in text: bonus -= 2.0` 模式一致。

不重写 answer_api 主链路组装逻辑，只在 evidence 排序加分层加一条降权规则。

## 3. 验证（improved / regressed cases）

### 3.1 [6] 改善（质量提升，仍 fail）

| | 前 | 后 |
|---|---|---|
| 答案 | 山博轩，杨郁 DOI: 10.12677/sg.2024.142002...comprehensive energy systems...Keywords V2G | 标准最初由日本汽车制造商和电力公司共同开发,可支持双向充电,适合于V2G 场景应用。 |
| cov | 0.15 | 0.23 |
| pass | False | False |

答案从学术元数据变成实质内容——质量改善（诚实化），但 [6] 仍 fail（措辞对齐问题：
expected_point「移动分布式能量存储...源荷储三重属性...双向通信双向输能」的完整表述不在任何
证据里，证据只有碎片化提及）。

### 3.2 [14] 回归（去 artifact，诚实化）

| | 前 | 后 |
|---|---|---|
| 答案 | 期刊元数据「Smart Grid 智能电网, 2024...comprehensive energy systems V2G」 | 实质内容「标准最初由日本汽车制造商...可支持双向充电，适合于V2G场景」 |
| cov | 0.34 | 0.22 |
| pass | True | False |

[14] 之前 pass（0.34）是 **artifact**：期刊元数据证据含「智能电网」「V2G」等 token，与
expected_point（「V2G技术为智能电网提供服务」）共享，假通过。降权后答案变实质内容，没覆盖
「智能电网服务」表述，诚实 fail。这与防降级（P3）同类——去 artifact。

## 4. pass_rate 影响

| | P3+防降级后 | +元数据降权后 |
|---|---|---|
| 20q pass_rate | 0.40（8/20） | 0.35（7/20） |
| 变化 | — | -0.05（[6] 仍 fail + [14] 去 artifact -1 pass） |

净效果 -1 pass。按 Sprint 3「不刷分、诚实」原则，0.35 是去 [14] artifact 后的诚实值，
质量上 [6] 答案更好（实质内容 vs 作者+DOI）。用户已确认保留降权（诚实优先）。

## 5. 边界合规

- ✅ 不重写 answer_api 主链路组装（只加 evidence 排序降权规则）
- ✅ 不删 expected_points 数据
- ✅ answer_changed_by_ontology 仍 false
- ✅ 改进/回归案例均已记录（[6] improved, [14] regressed=去 artifact）
- ✅ 诚实优先：去 [14] artifact 假通过，接受 pass_rate -0.05

## 6. 后续

- [6] 措辞对齐问题（expected_point 完整表述不在证据里）需 WP3 召回增强或 parse 层解决。
- DOC-000013 论文类文档的元数据块应在 ingest 阶段更彻底过滤（`_is_academic_header_noise`
  阈值过严，漏过长 abstract 块），属后续工程债。
