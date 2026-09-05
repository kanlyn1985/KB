# D6-DESIGN-REVIEW-001 — Design Review: Hysteretic Developmental Regime Separation

- Date: 2026-09-04 · Reviewer: independent design review（AI 执行）
- Project: Yilife · Branch: design/developmental-core-v1 · HEAD: **9dacc0d**（D5 correction）
- D5 execution substrate: 5096ec5（frozen）· D5 carrying commit: 82b744e（frozen）
- Nature: DESIGN REVIEW ONLY——零 runtime 修改、零 genome 修改、零 D5 artifact 修改、
  零实验执行

## 1. Repository Inspection Findings（以实际 repo 内容为准）

- D5 correction 9dacc0d 确为 branch HEAD（fix(d5): correct checkpoint alignment and
  recompute frozen analysis）。修正后 statistics：DEFAULT P median=**5.8766**、
  mean=9.4321、CI95=[7.0250,12.3321]；g3_mut3 P median=**6.6883**、mean=7.7096、
  CI=[6.3386,9.2832]；bands DEFAULT 0/1/63、g3_mut3 0/0/64；verdict 维持
  MULTI_BLOCK_CARRIER_SUPPORTED。ρ/δ_postE1 对齐修复（PHASE_CHECKPOINTS=25、
  E2_RECOVERY_START=25、LATE_WINDOW=10、checkpointAt accessor）已实测落地。
- 可复用基础设施（D6 直接消费，零新建模）：三臂 runner（runSeedTriple/runArm）、
  branch-point snapshot + guard G1（restore byte-equal）/G2（step-0 identical）、
  checkpointAt 对齐 accessor、D7 七维坐标（progression/progTarget/diffTimer/
  differentiation/population/structure/energy）、11 字段 internal block
  （assocMem/assocNet0/expectUS/csMem/expectPending/messenger_response/
  messenger_sensitivity/sensCap/proteome_dominant/proteome_diversity/proj_count）、
  bootstrapMean/permutationMean（seed 0xD5A2/0xD5A1, n=2000）、64-seed sealed cohort、
  sha256 manifest 纪律、tests/d5-*.test.mjs harness。
- State variable 分类（D6 可用面）：
  A. external/environment：env.r 字段（checksum/min/mean/max 逐 checkpoint 记录）；
  B. developmental state：D7 七维 + devStage + population/e_mean 原始计数；
  C. internal state：11 INTERNAL_FIELDS；
  D. derived metrics：δ/ρ/R/P/bands/generalization/block decomposition
     （correction 后实现）。
- Permutation p=0 缺陷在 9dacc0d 中**未修**（p_value: extreme/n 仍可输出 0）——
  D6 protocol 必须改为 (k+1)/(N+1) 或 p<k/N 表述（STEP 13）。

## 2. D5 → D6 Scientific Transition

D5 corrected 结果（P median 5.88/6.69，远超 stable band 上限语义）表明：恢复后轨迹
对 E0 的偏离在 120 步恢复窗口内不仅未收敛，且按 protocol 口径为**强 lagged divergence**。
D5 的设计不能区分三件事：这种偏离是 (i) 缓慢瞬态弛豫（有限时间后回到 E0）、
(ii) 稳定的新动力学位形（regime/basin）、还是 (iii) 伪影。D6 的任务正是把
"persistent divergence"升级为可证伪的 basin/hysteresis 判据——**不是重新解释 D5，
而是检验 D5 现象的动力学分类**。

## 3. D6 Research Question（精确化）

采纳任务书推荐表述并修订一处（"reproducibly separated"操作化为跨 seed 几何一致性）：

> **D6-Q**：在有限环境扰动 E1 与逐字节恢复 E0 之后，系统是否在预注册的时间尺度
> T_medium/T_long 上保持在预注册的 E0 自漂移包络之外、且跨独立 seed 的恢复后状态
> 形成比同窗 E0 状态彼此之间更强的相互趋近（reduced dispersion）——即
> reproducible post-perturbation dynamical regime，而非延迟弛豫？

- Independent variable：环境程序（E0/E1/E2 及可选 E3/E4 arm 的 env.r 序列）；
- Intervention：单一全局 env.r ×0.4（D3/D5 同通道同量级；无其它通道）；
- Recovery condition：E0 字段 byte-for-byte 恢复（guard G1 延续）；
- Observation window：恢复后 T_short/T_medium/T_long 三层（STEP 6）；
- Primary endpoint：**normalized separation S(T) = δ(T)/d_E0-selfdrift(T)** 在
  T_long 的窗口均值（唯一 primary；其余全 secondary）；
- Null H0：S(T_long) ≤ S_threshold（预注册，=2，即 E0 包络外判据的延续）且
  恢复后轨迹与 E0 的距离趋势斜率 ≤0（收敛中）；
- Alternative H2：S(T_long) > 2 且跨 seed 几何一致性判据（STEP 8 C/D/E）成立，
  且斜率不显著异于 0 或为正（无收敛趋势）。

## 4. Competing Hypotheses（互斥、可证伪）

| 假设 | 内容 | 判别信号 |
|---|---|---|
| H0 transient relaxation | 偏离是噪声/瞬态，向 E0 收敛 | S(T) 随 T 递减趋于 ≤1；恢复后轨迹与 E0 距离斜率显著负 |
| H1 extended relaxation | 有限但更长的弛豫（超出 D5 的 120 步窗） | T_medium 仍偏离但 T_long 斜率显著负且 S 下降跨越阈值 |
| H2 persistent regime/basin | 恢复后进入可复现的分离动力学位形 | S(T_long)>2 持续、斜率 ≈0/正、跨 seed 恢复后相互距离 < 与 E0 距离、E4 二次扰动可区分路径依赖 |
| H3 artifact | 测量耦合/数值漂移/环境不匹配 | environment checksum 不等（应被 G1 拒绝）；branch-point 状态不等（G2）；同 seed 同 arm 重放不确定；E0 自漂移本身量级与 δ 同阶且方向系统性 |
| H4（新增）回归均值伪影 | E2 恢复段落在 E0 轨迹的"远端"仅因 E0 轨迹自身晚期漂移方向 | S 用 per-seed E0 自漂移归一后消失；permutation 标签交换检验不显著 |

判别设计必须能同时排除 H0/H1/H3/H4 才能支持 H2——任何单一信号不足。

## 5. Operational Basin Definition（任务书 STEP 4 修订）

任务书草稿三条件方向正确但不足——"outside E0 envelope"不能推出 basin。修订为
**四层操作定义**（全部预注册）：

- **B1（分离性）**：post-recovery 轨迹在 [T_medium, T_long] 全窗保持
  δ(t) > 2×d_E0-selfdrift(t)（per-seed 归一，S>2）；
- **B2（稳定性）**：B1 窗内 δ(t) 对 t 的线性回归斜率 95% CI 包含 0 或为正
  （无向 E0 收敛趋势）；
- **B3（凝聚性）**：跨 seed 的 post-recovery 状态（同 arm 同时刻）平均两两距离
  **小于**它们与 matched E0 状态的平均两两距离（ratio < 1，permutation 检验）——
  这是"进同一个 regime"而非"各自随机漂远"的关键证据；
- **B4（离散性/分岔证据）**：E4 双向扰动 arm（若执行）显示恢复终态对扰动方向/幅度
  的离散化响应（两 arm 终态间距 > 各自 E0 self-drift）——basin 边界的直接证据。
  无 E4 时 B4 降级为"未测"（H2 降为"persistent regime supported, basin boundary
  untested"）。

"alternate developmental basin"仅在 B1–B4 全部成立时使用；B1+B2+B3 成立而无 B4 时
只允许表述"persistent separated developmental regime (boundary untested)"。
**"outside E0 envelope"单独绝不构成 basin 声明。**

## 6. Hysteresis Definition（可计算、非装饰数学）

- **Hysteresis loop distance**：forward path（E1 phase，E0→受扰态）与 recovery path
  （E2 phase，受扰态→恢复态）在同一状态空间的路径积分不对称性：
  `HL = Σ_{t∈E1} δ_fwd(t) − Σ_{t∈E2rec} δ_rec(t)`，其中 δ_fwd 沿 E1 轨迹对 E0 网格、
  δ_rec 沿 E2 恢复段对 E0 网格（同 checkpoint 对齐——correction 后 accessor 直接复用）。
  HL>0 且显著（per-seed paired permutation，(k+1)/(N+1) 报告）= 恢复路径未沿原路
  返回 = hysteresis 证据；
- **Return-map asymmetry**：E2 endpoint 与 E0 endpoint 的距离 vs E1 endpoint 与
  E0 endpoint 的距离之比随时间的三点比较（D5 已有量，D6 仅延长时间轴）；
- 禁止引入比路径积分/三点比较更复杂的指标（无 PCA-loop/熵/拓扑量——避免不可预注册
  的自由度）。

## 7. Experiment Matrix

| Arm | 程序 | 目的 | 必要性 |
|---|---|---|---|
| E0 | 无扰动 240 步（**关键升级：D5 只落盘 120 步**） | B1/B3 基线包络 + H0/H4 对照 | 必须 |
| E1 | ×0.4 → 120 步 | 扰动臂 | 必须 |
| E2 | ×0.4 → 恢复 → 240 步恢复观察 | 主检验臂（T_long 窗） | 必须 |
| E3 | ×0.4 → 恢复 → **再 ×0.4 → 再恢复** | 可重复性/路径依赖（同一 basin 可再入） | 推荐（区分 H1/H2 的最强单臂证据） |
| E4 | **反向扰动**（env.r ×2.0，若 channel 支持上界安全）→ 恢复 | B4 basin 边界离散化 | 可选（无强科学理由不加） |
| E5 | sham（读 env.r 但不写）| sham control（STEP 11-6） | 推荐（零成本） |

E0 必须 240 步是本轮最重要设计修正：D5 的 E0 只记录 120 步，导致 corrected ρ 的
E0 基线窗只能用 E1 末点/平移近似——D6 用**真实 E0 同物理步对照**消除该缺陷。
E3 是区分 H1（一次长弛豫）与 H2（可再入 regime）的决定性臂：H1 预言第二次恢复后
S 显著低于第一次；H2 预言 S 可复现。

## 8. Primary / Secondary Metrics

- **PRIMARY（唯一）**：S(T_long) = mean_{T_long 窗} δ(t)/d_E0-selfdrift(t)，
  per-seed 计算、per-genome 聚合（median 报告 + mean 的 pair-bootstrap CI——
  明确标注 CI 统计量，吸取 D5 教训）；
- Secondary（全部预注册、不参与 verdict 分支）：δ(t) 绝对轨迹距离、d_E0(t) 自漂移、
  收敛斜率（B2）、recovery slope、cross-seed clustering ratio（B3）、
  到 E0 轨迹 vs 到 post-perturbation cluster 中心的距离（B3 补充）、
  state-space occupancy（D7 各维 per-checkpoint 分布对比，descriptive）、
  return-map（D5 延续）、hysteresis loop distance HL、late-window stability；
- 禁止：多指标挑显著（门控顺序预注册；primary 不显著 → verdict 只能是
  INCONCLUSIVE/NOT_SUPPORTED，secondary 不得救）。

## 9. Statistical Plan（预注册）

- Estimand：median S(T_long) per genome（primary）；mean S(T_long) 附 pair-bootstrap
  CI（2000, seed 0xD6A2）——**标注"CI of mean S"**；
- Permutation：within-seed label permutation（2000, seed 0xD6A1）；
  **p 报告 = (k+1)/(N+1)**（修正 D5 的 p=0 缺陷）；
- Multiple comparisons：primary 单检验无校正；secondary 全部 descriptive
  （不作 verdict 输入）——门控策略预注册；
- Seed-level aggregation：median/mean 双报；band 判定用 per-seed S 与 aggregate 双轨；
- Missing data：任何 seed 任一 arm guard 失败 → 该 seed 全臂剔除（同 D5）；
  valid seeds < 24/genome → INCONCLUSIVE；
- Thresholds：S>2（包络外，延续 2× self-drift 约定）；B2 斜率 CI；B3 ratio<1；
  全部在执行前冻结；
- Stopping rule：无中期窥视；一次执行 n=64；若 INCONCLUSIVE 仅允许按预注册
  增补臂（E3/E4）重跑一次并声明为 exploratory——不允许加 seed 至显著。

## 10. Falsification Criteria

- H0 成立（→ D6 NOT_SUPPORTED）：S(T_long) ≤ 2 或 B2 斜率显著负；
- H1 成立：T_medium 偏离但 T_long 斜率显著负且 S 下降——**即使 B1 在 T_medium 成立
  也不是 basin**；
- H2 成立：B1∧B2∧B3（∧B4 若执行）全部成立；
- H3 成立（→ 全部结果作废）：G1/G2 任一失败、同 seed 重放 checksum 不等、
  E0 自漂移与 δ 同阶且系统性同向；
- H4 成立（→ H2 拒绝）：归一化后 S 不再 >2 或 permutation 不显著；
- **自我证伪保障**：primary endpoint 唯一且预注册；E3 臂显式检验可再入性——
  若 E3 恢复后 S 下降，H2 被削弱（结果即证伪）。

## 11. Negative Controls

1. no-perturbation control = E0 240 步（基线+包络）；
2. environment checksum restoration control = G1 延续（逐 checkpoint checksum）；
3. branch-point state equivalence control = G2 延续（step-0 identity 三臂）；
4. numerical reproducibility check = 同 seed 同 arm 重放 checksum 全等（D5 纪律）；
5. E0 self-drift control = d_E0(t) 逐 seed 逐 checkpoint（B1/B3/E 归一分母）；
6. sham perturbation control = E5（读写路径全同、只差写动作）。
全部控制臂失败 → 对应主臂数据作废（fail-closed）。

## 12. Causality Boundary（STEP 12 声明）

D6 即使支持 basin/hysteresis，语言边界仍为：
"environment history produces a reproducibly separated, persistent developmental
dynamical regime (path dependence / hysteresis)"。
**不得声称**：internal state causal carrier（D4-R3-R3 反事实干预 = DEVELOPMENT_MEDIATED
——内部状态移植未改变转移，故 D6 的持续偏离应解读为 developmental dynamical
persistence 而非 internal causal memory）、memory、learning、adaptation、agency、
intelligence、fitness。D6 的 block decomposition（若报告）仅是 descriptive 移位测量，
不是因果归因。

## 13. Artifact Specification（STEP 15）

D6_PROTOCOL.md（预注册全文，执行前冻结）/ D6_DESIGN_REVIEW.md（本文档）/
D6_HYPOTHESES.md（H0–H4 与判别矩阵）/ D6_METRICS_SPEC.md（primary/secondary 定义
+ checkpoint 对齐规范——继承 9dacc0d accessor）/ D6_STATISTICS_SPEC.md（estimand/
bootstrap/permutation/(k+1)/(N+1)/门控/缺失处理）/ D6_ARTIFACT_SCHEMA.md
（branch_records 含 E0 240 步完整落盘——**修正 D5 落盘截断**；E3/E4 arm schema）/
D6_SEED_POLICY.md（64 sealed cohort 复用 + E3/E4 同 cohort；新独立 cohort 仅在
validation split 时引入）/ D6_REPRODUCIBILITY.md（重放 checksum/浮点确定性/环境
ledger）/ D6_DESIGN_REVIEW_REPORT.html / hash manifest。
E0 240 步完整落盘是 D6 artifact schema 相对 D5 的**必须修正项**。

## 14. Implementation Blockers（STEP 16——记录不偷改）

| # | Blocker | 影响 | 处置 |
|---|---|---|---|
| B-1 | D5 runtime E0 只落盘 120 步（phase-2 缺失）——D5-STAT-REPAIR-001 的 STOP 根因 | D6 E0 包络/H0/H4 对照必须 240 步 E0 | D6 runner 必须实现 E0 240 步完整落盘（新代码，不回改 D5） |
| B-2 | permutationMean 返回 p=0（k=0 时） | 统计表述 | D6 统计层改 (k+1)/(N+1)（新代码） |
| B-3 | E2 cp24 重复标签（cosmetic off-by-one，9dacc0d 已按 index 对齐绕过） | D6 schema 应修复标签生成 | D6 runner 修 cpOffset（新代码） |
| B-4 | E4 反向扰动需确认 env.r 上界安全（×2.0 是否越系统有效域） | E4 可行性 | 实现前须 env.r 值域审计；无审计则砍 E4 |

## 15. Recommendation

**READY_FOR_IMPLEMENTATION**（附条件：D6_PROTOCOL.md 按本评审 §3–§13 冻结，
B-1/B-2 在 D6 实现期以新代码解决，E4 以 env.r 值域审计为前置）。

## 16. Final Scientific Standard（STEP 18 三态判定条件）

- **Hysteresis：SUPPORTED** 当 HL>0 显著（(k+1)/(N+1)）且 B2 成立（未沿原路返回且
  无收敛趋势）；INCONCLUSIVE 当 HL 方向一致但不显著；NOT_SUPPORTED 当 HL≤0 或
  显著负（恢复路径更近 E0）；
- **Persistent developmental regime：SUPPORTED** 当 B1∧B2∧B3 在 T_long 成立；
  INCONCLUSIVE 当 B1 成立但 B3 不显著；NOT_SUPPORTED 当 S≤2 或收敛斜率显著负；
- **Alternate developmental basin：SUPPORTED** 当上述成立**且** B4（E3 可再入 +
  E4 离散化）成立；INCONCLUSIVE 当 regime 成立但边界未测（缺 E3/E4）；
  NOT_SUPPORTED 当 B3 失败（跨 seed 无凝聚）或 H4 成立；
- 语言红线：以上任何 SUPPORTED 均不得表述为 memory/learning/adaptation/agency/
  intelligence/internal causal carrier/fitness（D4-R3-R3 边界延续）。