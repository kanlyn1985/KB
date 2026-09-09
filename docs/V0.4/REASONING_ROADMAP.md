# V0.4 Reasoning Roadmap

- Document ID: AKB-DD-V04-004 · Status: Design Baseline
- 前置：V0.3 FINAL — ACCEPTED / FROZEN；本路线图仅设计，实现须另开实现任务书
  （AKB-V04-IMPL-001 起逐门验收，同 V0.2/V0.3 先例）。

## 1. 阶段规划

| 阶段 | 内容 | 验收门 |
|---|---|---|
| V0.4-IMPL-001 | ReasonerProvider Protocol + BuiltinRuleReasoner（RR-01..04）+ ReasoningEngine 编排（parent selection/环检测/fingerprint 锚/SAVEPOINT 原子） | RS-CMP-001..010 全 PASS |
| V0.4-IMPL-002 | migration 14（akb_reasoning_runs）+ trace_inference_chain + provenance 双链 | DRY-RUN 就绪 + trace 等价性测试 |
| V0.4-IMPL-003 | 治理集成（inferred→validated 人工流；inferred→asserted 禁止回归）+ failure isolation 加固 | 治理面回归零破坏 |
| V0.4-IMPL-004 | Golden 数据集（推断案例 P/N/D 分层）+ 全量回归 + CI 取证 | repository PASS + CI 双绿 |
| V0.4-FINAL-001 | 独立评审 + 终验报告 | ACCEPTED — RELEASE BASELINE |

## 2. 里程碑依赖

- migration 14 仅在 V0.4-IMPL-001 行为验证后落库（additive；V0.1/V0.2/V0.3 表零改动）；
- 生产执行窗口继续走批准制（与 migration 12/13 同窗候选）；
- 外部/LLM reasoner 接入排在内置规则引擎稳定之后（stochastic but traceable）。

## 3. 测试计划概要（实现期展开为任务书）

- 生命周期：inferred 恒 candidate / inferred→asserted 拒绝（State Machine 回归）/ 
  candidate→validated 人工流；
- 规则输入输出：RR-01..04 各自输入/输出/负例（malformed parent、缺 derivation、
  跨 run 环、深度超限）；
- provenance：五级链完整（Candidate→Run→Parents→Evidence→Document）、
  rule_input_snapshot 回放等价、trace_inference_chain 确定性；
- 隔离：provider crash / malformed proposal / run 失败零候选；
- 回归：V0.1/V0.2/V0.3 全量（含 Golden 30/40/55）零下降。

## 4. 风险登记（设计期）

| 风险 | 缓解 |
|---|---|
| 链式推理爆炸 | DC-06 MAX_DEPTH + run 级提案上限（继承 V0.3 capped 语义） |
| LLM reasoner 不可复现 | rule_input_snapshot 全记录；LLM 仅在 traceable 模式接入（后阶段） |
| inferred 污染 parent 池 | DC-02 一阶限定 + 环检测 |
| 治理负担增加 | inferred→validated 仅人工；报告聚合视图（实现期） |

## 5. 与既有 INV 的兼容声明

V0.4 设计不引入任何新的状态跃迁、不放宽任何现有禁止项、不新增 authoritative 写路径、
不触碰 EvidenceSet/SynthesisRun 语义、不改 temporal semantics。