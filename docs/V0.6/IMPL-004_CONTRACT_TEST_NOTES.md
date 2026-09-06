# V0.6 IMPL-004 Implementation Notes — Contract Test Suite

- Date: 2026-09-04 · Baseline: 749b58e（IMPL-003）· V0.5 frozen e7a286e（零触碰实测）
- 新增：agent_kb_core/tests/v06_contract/test_v06_contract.py（CONTRACT-CMP-001..020）

## 套件定位

VC/OC/PC（30 项）覆盖单元面；CONTRACT-CMP-001..020 覆盖**跨模块集成/不变量面**：
全链路贯通、identity 一致性、rebuild 稳定性、错误分类学、governance actor 矩阵、
depth 独立性、migration 完整性、V0.5 isolation final。

## CONTRACT-CMP-001..020（全 PASS）

| # | Contract | 验证点 |
|---|---|---|
| 001 | full chain | Context→Orchestrator→Engine→ProvenanceTrace 一次贯通 |
| 002 | deterministic identity | 同输入→同 context_id/fingerprint/candidate_id/trace |
| 003 | fingerprint anchor replay | V0.4 fingerprint 公式独立复算一致 + 重放零新候选 |
| 004 | provenance closure integrity | verify_closure 全闭环 + 五问（What/Why/From/Context/Version） |
| 005 | trace to evidence/document | 候选并集→全部 evidence/document 实存 |
| 006 | candidate lifecycle | 恒 inferred/candidate；→asserted 禁；→validated 开放 |
| 007 | governance boundary | 零 status 变更审计；validator 通道完好 |
| 008 | status/temporal boundary | rejected/hypothesized 排除；temporal 只读引用 |
| 009 | fail-close matrix | root/hops/status/limit/depth/ghost 全显式拒绝 |
| 010 | no LLM dependency | 三模块源码审计零 LLM/网络；provider deterministic |
| 011 | read-only kg | 全链路后 kg 四表零变化；provenance 增量仅审计类 |
| 012 | canonical view stable | V0.5 canonical view 跨全链路不变 |
| 013 | legacy isolation | API 面互斥 + graph_edges 零变化 |
| 014 | rebuild pipeline stable | 同 fingerprint 重 persist 幂等命中 + 全链路结果不变 |
| 015 | migration chain untouched | 15 版本唯一 + migration 14 完好 + 零 V0.6 专表 |
| 016 | cross-instance pipeline | 双实例全链路全等 |
| 017 | error surface taxonomy | E-V06-* 命名空间统一 + 不吞异常 |
| 018 | depth independence | reasoning depth 4 ≠ query depth 8（各自边界实测） |
| 019 | governance actor matrix | system/agent/llm 零晋升 + EntityGovernance human-only 回归 |
| 020 | V0.5 isolation final | 双全链路后 kg 快照/canonical view/query 计数零漂移 |

## 过程修复（V0.6 阶段内）

- provenance.py trace_candidate 的 rule_version 提取：V0.4 rule_ref 形如
  "RR-02@v04-rules-v1"——从 ref 提取 version（单一事实源，零新字段）；
- contract 断言的 akb_provenance 列索引修正（activity=第 4 列）。

## 遗留（不变）

- P1（IMPL-001 notes）：fingerprint 变化 + 相同 node_id 的全量 repersist PK 冲突——
  CONTRACT-CMP-014 只锚定同状态重建幂等语义（V0.5 frozen，待 owner 决策）。