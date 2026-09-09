# step3 懒拆叶子细挂边草稿（36 条）

> ✅ 已落地（2026-08-25）：35 条边已合并进 `skeleton_v0.6.json`（208→243 边），结构尺 7/7。
> 工装治具按方案 2 重归类为 `G-METHOD-FIXTURE`（方法节点，不挂边）。

> 目的：给 36 个懒拆叶子挂细边，使结构尺 7/7 全绿。
> 本稿供人工评审；「低」置信度的边（工装治具）请重点确认。
> 落地方式：评审通过后合并进 `skeleton_v0.6.json` 的 `relations`。

## allocate（19 SWC ← L 逻辑）

| 来源 | 目标 | 置信 | 理由 |
|------|------|------|------|
| `L-STATE` | `P-SW-ASW-ACRELAY` | 高 | AC Relay 状态机（L-STATE 明确含） |
| `L-SYS` | `P-SW-ASW-AUXPWR` | 中 ⚠️ | 辅助电源=电源管理 |
| `L-STATE` | `P-SW-ASW-CC` | 高 | 控制导引状态机（F-OBC-CP→L-STATE） |
| `L-STATE` | `P-SW-ASW-CP` | 高 | CP 充电握手状态机 |
| `L-STATE` | `P-SW-ASW-CPOUT` | 中 ⚠️ | CP 输出，属 CP 状态链 |
| `L-FAULT` | `P-SW-ASW-DEH` | 高 | 特殊故障上报（ASIL B/休眠前存储/整车交互，已核实） |
| `L-STATE` | `P-SW-ASW-ELECLOCK` | 高 | 电子锁开关控制+故障检测（已核实） |
| `L-STATE` | `P-SW-ASW-GUNMANAGE` | 高 | 枪管理状态机 |
| `L-SENSE` | `P-SW-ASW-GUNTEMP` | 高 | 枪温度采样 |
| `L-PWRCTRL` | `P-SW-ASW-HVDM` | 中 ⚠️ | 高压放电管理（HVDM 板，已核实） |
| `L-FAULT` | `P-SW-ASW-INTERLOCK` | 中 ⚠️ | 高压互锁断开=故障判定 |
| `L-STATE` | `P-SW-ASW-LED` | 高 | 充电状态指示 |
| `L-COMM` | `P-SW-ASW-NACS` | 高 | 北美充电标准=协议 |
| `L-PWRCTRL` | `P-SW-ASW-ORINGOVP` | 中 ⚠️ | ORing 过压保护=功率级 |
| `L-STATE` | `P-SW-ASW-S2` | 高 | CP 电路 S2 开关状态 |
| `L-COMM` | `P-SW-ASW-UDMANAGE` | 高 | UDS Manage 诊断管理（已核实） |
| `L-COMM` | `P-SW-BSW-DIAG` | 高 | 诊断 DCM/DEM/UDS |
| `L-SYS` | `P-SW-BSW-MEM` | 中 ⚠️ | 存储 NVM/Flash=系统自检 |
| `L-SYS` | `P-SW-RTE` | 中 ⚠️ | RTE=运行时集成层 |

## produce（9 工艺 → P 物理件）

| 来源 | 目标 | 置信 | 理由 |
|------|------|------|------|
| `G-PROD-ASSEMBLY-FASTEN` | `P-HW-MECH-FASTENER` | 高 | 螺纹紧固→紧固件 |
| `G-PROD-ASSEMBLY-PRESS` | `P-HW-MECH-CONNECTOR` | 高 | 压装压接→连接器/插接 |
| `G-PROD-ASSEMBLY-BOND` | `P-HW-MECH-SEAL` | 高 | 涂胶密封→密封系统 |
| `G-PROD-ASSEMBLY-GEN` | `P-HW-MECH` | 中 ⚠️ | 通用组装→结构件 |
| `G-PROD-ASSEMBLY-FIXTURE` | `P-HW-MECH` | 低 ❓ | 工装治具=工具非产件；暂挂结构件，待确认 |
| `G-PROD-POTTING-POT` | `P-HW-THERMAL-POT` | 高 | 灌封→灌封涂覆件 |
| `G-PROD-POTTING-DISP` | `P-HW-THERMAL-POT` | 高 | 点胶涂覆→三防/涂覆件 |
| `G-PROD-POTTING-SEAL` | `P-HW-MECH-SEAL` | 高 | 密封胶→密封系统 |
| `G-PROD-POTTING-THERMAL` | `P-HW-THERMAL-TIM` | 高 | 导热材料→导热界面材料 |

## verify（7 验证 → P/R）

| 来源 | 目标 | 置信 | 理由 |
|------|------|------|------|
| `G-VERIFY-CAE-THERMAL` | `P-HW-THERMAL-HEATSINK` | 高 | 热仿真→散热器 |
| `G-VERIFY-CAE-STRUCT` | `P-HW-MECH-HOUSING` | 高 | 结构仿真→壳体强度 |
| `G-VERIFY-CAE-VIBRATION` | `P-HW-MECH-BRACKET` | 高 | 振动仿真→支架模态 |
| `G-VERIFY-CAE-FLUID` | `P-HW-MECH-WATERWAY` | 高 | 流阻流体→水道 |
| `G-VERIFY-VIBRATION-VIB` | `P-HW-MECH-HOUSING` | 高 | 振动测试→壳体 |
| `G-VERIFY-VIBRATION-SHOCK` | `P-HW-MECH-HOUSING` | 高 | 冲击跌落→壳体 |
| `G-VERIFY-VIBRATION-COND` | `R-ENV` | 中 ⚠️ | 试验条件(PSD/GRMS)来自环境需求 |

## issue-on（1 客诉 → P）

| 来源 | 目标 | 置信 | 理由 |
|------|------|------|------|
| `Q-PROBLEM-CUSTOMER` | `P-ROOT` | 中 ⚠️ | 客诉针对整个产品 |
