# D5-STAT-AUDIT-001-RESTART — Statistical Consistency Audit Report

- Date: 2026-09-04 · Auditor: independent read-only audit（AI 执行）
- Source: https://github.com/kanlyn1985/Yilife.git · branch design/developmental-core-v1
- Frozen baseline: **82b744e8d8fb3861e3ab54961b166307e3805356**（git show 只读；零 checkout/merge）
- Artifact root: reports/d1-history-dependence/d5-adaptive-agency-formal-v1/

## 1. Artifact Inventory & Hash Verification

```text
tracked + hash-verified（sha256.txt 逐项比对）: 9/10
  D5_RESULT.html ✓ D5_manifest.json ✓ audit.md ✓ manifest.json ✓ protocol.md ✓
  seed-list.json ✓ statistics.json ✓ trajectories.jsonl ✓ verdict.json ✓
absent runtime-only: raw.log（sha256.txt 有记录但 git 对象不存在——P2 记录，
  审计按缺席处理，未生成/未伪造）
hash mismatches: 0
```

## 2. 每项统计：reported vs independently derived

### DEFAULT（n=64）

| 统计量 | reported | independently derived | 一致性 |
|---|---|---|---|
| mean δ | 0.0109362 | 0.0109362（cp5..23 窗——protocol"6–25"1-based） | ✓ |
| δ CI95 | [0.0087979, 0.0132473] | 独立 bootstrap 同带（变异内等值） | ✓ |
| perm p | 0 | N=2000、k=0 → p < 1/2000 = 0.0005 | ✓（表述问题见 §4） |
| R median | 1.3998907 | per-seed R 复算一致（校准窗 cp14..23） | ✓ |
| P median | 1.0744067 | **1.0744067**（per-seed persistence 字段中位数） | ✓（数值一致） |
| P bootstrap point | 1.1988942 | per-seed P 的 **mean** = 1.1988942 | ✓ |
| P CI95 | [1.0982, 1.3268] | per-seed P 的 pair-bootstrap **mean CI**（3 种子独立复算
  [1.092,1.326]/[1.096,1.323]/[1.099,1.320]——报告值在变异带内） | ✓ |
| stable/partial/reversion | 63/1/0 | 复算一致 | ✓ |
| generalization fraction | 0 | per-seed generalized 全 false | ✓ |

### g3_mut3（n=64）

| 统计量 | reported | independently derived | 一致性 |
|---|---|---|---|
| P median | 1.04027285 | 1.0402729 | ✓ |
| P mean / boot point | 1.1671522 | 1.1671522 | ✓ |
| P CI95 | [1.0189, 1.3360] | 独立 bootstrap [1.0258, 1.3358]（变异带内等值） | ✓ |
| mean δ / perm p | 0.0126077 / 0 | 同 DEFAULT 语义 | ✓ |
| generalization fraction | 0.015625 | （1/64 seeds） | ✓ |

## 3. DEFAULT P median / CI 详细诊断（主问题）

**结论：A 类内部一致——1.07 与 [1.10,1.33] 来自同一 frozen 统计对象（64 个 per-seed
P 值）的两个不同统计量，表面矛盾不成立。**

- P median = 1.0744067 = median(per-seed P)（实测复算精确一致）；
- P CI95 = [1.0982, 1.3268] = **mean(per-seed P) 的 pair-bootstrap percentile CI**
  （bootstrap point=1.1988942 恰为 per-seed P 的 mean——实测复算精确一致；
  独立三种子 bootstrap 复现在报告值变异带内）；
- P 分布右偏（median 1.0744 < mean 1.1989；min 0.637 / max 3.53）——mean 的 CI
  不覆盖 median 是正常统计现象，非字段错位、非 rounding、非 JSON→HTML 错误；
- median 的 bootstrap CI（独立复算）=[1.0231, 1.1216]——包含 1.0744，自洽；
- HTML（D5_RESULT.html，2194 字节摘要表）只展示 median P=1.0744，**未展示 CI**，
  无列错位/行交换/陈旧生成问题；
- 观察构成：P 为 **per seed**（64 个观测，arm A primary，2 genome 分列）；
  median=64 值的中位数；CI=同 64 值的 pair resample(2000) 均值区间（protocol §6.3
  "judged with bootstrap CI on P"）。

## 4. Permutation p-value 诊断

- statistics.json：permutations=2000、p_value=0（DEFAULT 与 g3_mut3 同）；
- 协议：within-seed paired sign/permutation (2000, seed 0xD5A1) vs 0；
- k=0 exceedances → 无 +1 校正的实现输出 p=0；
- 数学正确表述：**p < 1/2000 = 0.0005**（加法校正后 p = 1/2001）；
- 判定：**display convention 问题（P2）**——"0"是实现原始值（k=0→p=0 的直接序列化），
  非 substantive error；是否修订为 p<1/N 交验收决定（本审计不改）。

## 5. Block Decomposition 复算（trajectories.jsonl 独立复算）

DEFAULT，E2 末点 vs E0 cp23 平均绝对偏移：

```text
D block:      population 0.1999（≈0.18–0.20 ✓）  structure 0.1579（≈0.17 ✓）
              energy 0.1668（≈0.15 ✓）
internal:     proteome_diversity 3.5312（3.5–4.1 ✓）  messenger_sensitivity 0.2558
              （0.26–0.29 ✓）  assocNet0 0.0732（0.07–0.10 ✓）
```

全部可从 frozen trajectories.jsonl 独立复算得到 ✓（非抄 statistics.json）。

## 6. Verdict 判据复核（protocol §8 逐条）

MULTI_BLOCK_CARRIER_SUPPORTED 预注册判据：
- (a) P in stable band（P>0.67，CI excluding 0.67）**both genomes**：
  DEFAULT stable=63/64、g3_mut3 stable 绝对多数；CI 下界 1.02/1.10 均 >0.67 → **PASS**
  （注：reported CI 为 mean-P 的 CI；median 口径下 median P 1.07/1.04 亦 >0.67——
  两口径同判）；
- (b) block-decomposable：D block（population/structure/energy）与 internal block
  （proteome_diversity/messenger_sensitivity/assocNet0）在 E2 endpoint 均超出
  within-arm drift 基线——§5 复算值与报告值吻合 → **PASS**；
- multi-genome condition（两 genome 同判）→ **PASS**。
- δ 显著性（permutation p<0.0005 + CI 全高于 noise floor 0.001）→ **PASS**。

**发现的统计缺陷是否改变预注册 verdict：见 §7。**

## 7. 发现的统计缺陷（Computation Error——不影响 verdict 方向）

**C-1（P1）：per_seed 的 `mean_rho_late` 与 `delta_post_e1` 两字段内容互换 +
P 语义错位。**

- 实测（64/64 seeds，DEFAULT）：statistics.json 的 `mean_rho_late` 值 =
  ‖D_E1(cp24) − D_E0(cp24)‖（这是 protocol 定义的 **δ_postE1**：E1→E2 切换点差异）；
  statistics.json 的 `delta_post_e1` 值 = ‖D_E1(cp23) − D_E0(cp23)‖（off-by-one
  checkpoint，非 T120）。
- 因此 per_seed 的 `persistence` = ‖E1(cp24)−E0(cp24)‖ / ‖E1(cp23)−E0(cp23)‖——
  **E1 相邻 checkpoint 漂移比**，不是 protocol 定义的 P = ρ_late / δ_postE1。
- 按 protocol 真语义重算（ρ_late = E2 恢复段末 10 checkpoint 对 E0 对应窗；
  δ_postE1 = cp24）：DEFAULT P median = **5.89**（vs reported 1.07），P mean = 9.43，
  CI95(mean) ≈ [7.06, 12.21]。
- **verdict 影响：无**。两种口径下 band 分布完全相同（reversion 0 / partial 1 /
  stable 63），P>0.67 且 CI>0.67 的 (a) 条件两口径均成立且更強（真语义 P 更大）；
  (b) block 判据与 δ 判据不受 P 字段影响 → **MULTI_BLOCK_CARRIER_SUPPORTED 在
  真语义下依然成立**（D 类排除）。
- 但注意：真语义下 P 的"stable band"解释（P≈1 = persistence，P≫1 = lagged
  divergence）与 protocol §7 的 surprising-if 分支（lagged divergence/hysteresis）
  相关——P≈5.9 属于**lagged divergence 强签名**，这改变了结果的**解读**
  （"stable adapted trajectory"→ 更接近"lagged divergence"），但不改变预注册
  verdict 分支（verdict 判据只按 band 与 block 条件）。该解读冲突记录为 P2。

**C-2（P2）：per_seed.delta_post_e1 使用 cp23（off-by-one）而非 T120=cp24。**
（与 C-1 同源——互换后残余的窗口错位。）

**P2：raw.log 不在 frozen git artifact set**（sha256.txt 有记录但对象缺席）——
permutation/运行日志类交叉验证受限。

## 8. Cross-Artifact Consistency

- statistics.json ↔ verdict.json：verdict/band/pBoot/perm 全一致 ✓；
- statistics.json ↔ D5_RESULT.html：HTML 摘要表（median P=1.0744、bands JSON、
  perm p=0）与 statistics 一致；HTML 无 CI 列 → 无 median/CI 错配展示 ✓；
- trajectories.jsonl ↔ statistics.json：per_seed P/band 逐 seed 对比 0 mismatch；
  mean_rho_late/delta_post_e1 字段互换（§7 C-1）✗（唯一不一致点）；
- D5_manifest.json：384 branch_records（3 arms × 2 genomes × 64 seeds）+ guard
  G1/G2 全 true，与 statistics guards(0 failures) 一致 ✓；
- audit.md：runtime SHA/seed-seal SHA/best-genome SHA 链完整 ✓。

## 9. Primary Classification

**C. COMPUTATION ERROR**（per_seed P 的字段互换 + off-by-one——§7 C-1/C-2）
**叠加 A（DEFAULT P median/CI 主问题本身 STATISTICALLY CONSISTENT——§3）**：
任务书主问题（1.07 vs [1.10,1.33]）的答案是 A；审计额外发现的真实计算错误是 C，
但 C 不改变 verdict 方向（D 类排除）。

## 10. P0/P1/P2

- P0 = 0（无证据损坏/无 frozen mutation/无 verdict 操纵/无数据丢失）
- P1 = 1（C-1：P 的字段互换语义错位——computation error；不改变预注册 verdict，
  但改变 P 的科学解读——lagged divergence 强签名 vs stable persistence）
- P2 = 3（raw.log 缺席；permutation p=0 展示约定；C-2 off-by-one 残余 +
  解读冲突注记）

## 11. Required Future Correction（repair 任务书范围——本审计不执行）

1. 修复 d5 统计实现：per_seed.mean_rho_late ← 真 ρ_late（E2 恢复段末 10 对 E0 对应窗）；
   per_seed.delta_post_e1 ← ‖E1(cp24)−E0(cp24)‖；重出 statistics.json/D5_RESULT.html；
2. 重审 verdict（预期不变：band/block/δ 条件在真语义下全部满足且更强）；
3. permutation p 展示修订（p<1/2000 或 +1 校正 p=1/2001）——验收决定；
4. 补 raw.log 入 git（或协议修订为 runtime-only 并从 sha256.txt 移除）。

## 12. 确认

- 零 checkout/merge/cherry-pick/rebase；frozen commit 82b744e 仅 git show 只读；
- 零实验工件修改（statistics/verdict/HTML/trajectories/protocol 均未动）；
- 本仓库工作树仅新增本审计文档；未重跑 D5；未自动修复；STOP after reporting。