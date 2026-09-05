# D5-STAT-REPAIR-001 — STOP Report（Repair Blocked — Baseline Data Insufficient）

- Date: 2026-09-04 · Baseline: 82b744e8d8fb3861e3ab54961b166307e3805356（frozen，零触碰）
- Audit basis: docs/audits/D5-STAT-AUDIT-001_RESTART_REPORT.md（9a28676）
- Classification: **STOPPED per §XXIII — repair not executable from frozen artifacts**

## 1. 执行前检查（§V）——全部通过

- repository/branch/HEAD ✓（28721cc→9a28676，working tree clean）
- frozen baseline 82b744e 可读（cat-file=commit）✓
- trajectories.jsonl 完整：128 行（DEFAULT 64 + g3_mut3 64），全部 status=OK，
  arm 形状一致（E0=25, E1=25, E2=50 records）✓
- protocol/statistics/verdict/audit 已读 ✓
- grep 定位：`experiments/developmental/d5-adaptive-agency.mjs`
  - L226-233 phaseDivergence（按数组下标取 records，上限 min(toCp, lenA-1, lenB-1)）
  - L239-249 delta/rho/deltaPostE1/persistence 计算
  - L244 deltaPostE1 = delta[delta.length-1].distance（= cp24 的 ‖E1−E0‖）
  - L249 persistence = meanRhoLate / deltaPostE1

## 2. Root Cause 深挖（实现层）

审计确认（64/64 seeds）：statistics.json 的
- `mean_rho_late` ≡ ‖D_E1(cp24) − D_E0(cp24)‖（= L244 deltaPostE1 的值）
- `delta_post_e1` ≡ ‖D_E1(cp23) − D_E0(cp23)‖（off-by-one checkpoint）
- `persistence` = 前者/后者（E1 相邻 checkpoint 漂移比——非 protocol P）

本轮新证据（trajectories.jsonl 落盘结构）：
- E0/E1 各 25 records（cp0..24）；E2 50 records（cp0..24 + cp24 重复 + cp25..48）
- **E0 的 phase-2 轨迹（E0 checkpoints 25..49）未落盘**——manifest 同（E0=25）
- 实现的 rho 窗口（L242：`phaseDivergence('E2','E0',25,49)`）在运行时需要
  E0 有 50 条 records；对落盘的 25 条 E0 该窗口为**空数组**

## 3. STOP 触发（§XXIII）

**修复 P 需要先修复 ρ_late；而 ρ_late 的 protocol 真语义
（ρ(t)=‖D_E2(t)−D_E0(t)‖，t=E2 checkpoints 26–50，protocol §6.2）
所需的 E0 phase-2 基线轨迹（checkpoint 25..49）不存在于任何 frozen artifact
（trajectories.jsonl 与 D5_manifest.json 的 E0 均只到 checkpoint 24）。**

具体验证（全部从 frozen 只读数据）：
1. 假设"E0 平移窗"（E2 cp39..48 ↔ E0 cp14..23 / cp15..24）→ ρ_late≈0.054-0.055，
   P≈5.88-6.19——**非** reported 1.1043；
2. 假设"E0 末端锚定"（ρ(t)=‖E2(t)−E0[cp24]‖）→ ρ_late=0.0623，P≈7.00——**非** 1.1043；
3. 穷举 E0 全部 10 宽对齐窗（36×16 组合）→ 无一命中 reported 0.008895；
4. 唯一 64/64 精确复现 reported `mean_rho_late` 的量 = dDistance(E1[cp24], E0[cp24])；
5. 因此 reported ρ_late 的**实现语义**无法从落盘数据重建其 protocol 语义计算路径，
   且 protocol 语义的输入数据（E0 phase-2）在 frozen artifact set 中缺失。

→ 触发 §XXIII-1（frozen trajectories 数据不完整：E0 phase-2 缺失）+
  §XXIII-2（protocol 语义虽可确定，但其计算所需的基线数据不可得，
  corrected P 无法从 frozen artifacts 独立验证）。
**按任务书要求 STOP——不生成 corrected statistics，不写 repaired report，
不 commit repair。**

## 4. STOP 原因分析（供决策）

- ρ_late 真值计算需要 E0 的 240 步轨迹；frozen 只有 E0 前 120 步（25 checkpoints）。
  三种可能：(a) 运行时 E0 确实跑了 240 步但落盘被截断（数据存在但未入 artifact）；
  (b) 运行时 E0 只跑了 120 步且实现的 rho 计算因 JS 数组越界/空数组语义产生了
  错误但非 NaN 的值（需审 JS mean 对空数组返回 NaN，与 JSON 非 null 矛盾——
  提示运行时数据与落盘不一致）；(c) E0 phase2 数据存在于某 runtime-only artifact
  （与 raw.log 同批未入库）。
- 任一情形下，**从当前 frozen artifact set 都无法按 protocol 真语义重建 ρ_late**。

## 5. 可选的解阻路径（需要 owner 决策，本任务不执行）

1. **恢复完整落盘**：从原始 runtime workspace（若存在）找回 E0/E2 的完整 50-checkpoint
   轨迹（与 raw.log 同批的 runtime-only 数据），作为补充 evidence 追加（不改 frozen
   commit，新增补充 artifact commit）→ 之后本 repair 可继续；
2. **协议澄清**：由 protocol owner 对"E0 基线在 E2 phase 的定义"作出书面澄清
   （E0 末端锚定/E0 平移窗/其它），并确认接受该语义的 corrected P
   （三种候选：P≈5.89 / P≈7.00 / 其它）→ 之后按澄清语义修复；
3. **接受 frozen 报告的局限**：将 C-1/C-2 缺陷永久记录为 P1 known-issue
   （verdict 方向不受影响——band 分布与 block/δ 判据在所有候选语义下一致），
   verdict 维持 MULTI_BLOCK_CARRIER_SUPPORTED 附注。

## 6. 本轮产出

- 本 STOP 报告（唯一新增工件；audit-only commit）
- 零代码修改；零 frozen 工件修改；零重跑；working tree clean

## 7. P0/P1/P2

- P0 = 0
- P1 = 1（延续：P 计算语义错误未修复——修复被数据缺失阻断）
- P2 = 3（raw.log 缺席 / p=0 展示约定 / delta_post_e1 off-by-one 残余）