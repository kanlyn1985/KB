> ⚠️ **已过期（stale）**：本表为 v0.6（19 缺口）。最新映射以 skeleton_coverage_map.json（v0.9，gap=0，85 要素全覆盖）为准，本 md 仅留档历史说明。

# 骨架覆盖映射表（工作包 → 骨架节点）

> 版本 0.6 | 边界：产品设计与验证知识 | 共 81 个工作包要素
> 完全覆盖 36 · 部分覆盖 26 · 真缺口 19（有对应节点 62/81 = 76.5%）

## REQ · 需求（5）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 产品需求分析（七大功能组） | `R-ROOT` | ✅完全 | R层12个需求域=需求分析产出 |
| 功能安全需求（SG/FSR/TSR/ASIL） | `R-FSC` | ✅完全 | 功能安全需求（SG→FSR→TSR→HSR/SSR） |
| 接口需求（CAN矩阵/连接器） | `R-IF` | ✅完全 | 接口与通信需求 + P-IF 接口树 |
| 客户标准解读（TS/SOR/SOW） | `R-STD` | ✅完全 | 标准条款（GB/T 40432 全量） |
| 需求追溯矩阵 | `G-PROC-STD` | 🟡部分 | ASPICE流程内含追溯，无独立节点 |

## EE · 电子EE（10）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 电子布局图 | `GAP` | ❌缺口 | 有电路拓扑(P-HW)，无布局工件节点 |
| 热损耗图 | `P-HW-THERMAL` | 🟡部分 | 有散热/导热，无器件损耗清单节点 |
| 安规设计表 | `R-SAFETY` | ✅完全 | 电气安全需求（绝缘/耐压/接触电流） |
| 主功率拓扑（PFC/LLC/输出/辅助） | `P-HW-OBC;P-HW-DCDC` | ✅完全 | PFC/LLC/辅助/EMI/变换/输出 已分解 |
| 原理图设计 | `GAP` | ❌缺口 | 无原理图节点 |
| PCBA Layout | `G-PROD` | 🟡部分 | 生产过程树含PCBA，无Layout设计节点 |
| 器件选型与降额 | `P-CAL;R-PERF` | ✅完全 | 标定数据树(降额曲线)+性能需求(降额) |
| 电路/磁仿真 | `G-METHOD-CAE` | 🟡部分 | 有热/结构/流阻仿真，无电路(SPICE)/磁仿真 |
| 磁性元件设计 | `P-HW-MAG` | ✅完全 | 磁件学科（变压器/电感） |
| 最坏情况电路分析 | `GAP` | ❌缺口 | 无WCCA节点 |

## SW · 软件SW（12）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| SYS.1 需求获取 | `G-PROC-STD` | 🟡部分 | ASPICE流程节点(SYS)，未分解到SYS.1 |
| SYS.2 系统需求分析 | `G-PROC-STD` | 🟡部分 | 同上 |
| SYS.3 系统架构设计 | `G-PROC-STD` | 🟡部分 | 同上 |
| SYS.4 系统集成测试 | `G-PROC-STD` | 🟡部分 | 同上 |
| SYS.5 系统合格性测试 | `G-PROC-STD` | 🟡部分 | 同上 |
| SWE.1 软件需求分析 SRS | `R-SW` | ✅完全 | 软件需求（SWRD） |
| SWE.2 软件架构 SWAD | `P-SW-ASW;P-SW-BSW` | 🟡部分 | 软件组件划分，无SWAD工件节点 |
| SWE.3 详细设计 DDS | `L-ROOT` | 🟡部分 | 逻辑组件树(白盒)，无DDS工件节点 |
| SWE.4 单元验证 | `G-PROC-STD` | 🟡部分 | ASPICE内，无软件单元测试节点 |
| SWE.5 集成验证 | `G-PROC-STD` | 🟡部分 | 同上 |
| SWE.6 合格性测试 MiL/SiL/HiL | `G-PROC-STD` | 🟡部分 | 无MiL/SiL/HiL节点 |
| SUP 支持过程 | `G-PROC-STD;G-METHOD-TOOL` | 🟡部分 | ASPICE SUP + 工具方法(gitlab/Polarion) |

## ME · 结构ME（14）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 结构设计方案（3D数模/BOM） | `P-HW-MECH;P-MECH` | ✅完全 | 结构件 + 结构学科零件分解 |
| 结构限制图 | `GAP` | ❌缺口 | 无结构限制图节点 |
| 热仿真报告（功耗+水道压降） | `G-VERIFY-CAE-THERMAL;G-METHOD-CAE-THERMAL` | ✅完全 | 热仿真验证+方法 |
| 力学仿真报告（静+动） | `G-VERIFY-CAE-STRUCT;G-METHOD-CAE-STRUCT` | ✅完全 | 结构仿真验证+方法 |
| 困气仿真 | `G-VERIFY-CAE-FLUID` | 🟡部分 | 流阻流体仿真，无独立困气节点 |
| 公差分析 | `G-METHOD-TOL` | ✅完全 | 公差分析方法（尺寸链/GD&T） |
| 安规检查表 | `R-SAFETY` | ✅完全 | 电气安全需求 |
| 结构七大物料 | `P-HW-MATERIAL;P-HW-MECH` | ✅完全 | 材料库 + 结构件 |
| 结构 DFMEA | `Q-FAILURE` | ✅完全 | 失效模式（FMEA相关） |
| 凝露分析 | `GAP` | ❌缺口 | 无凝露节点 |
| 气密测试 | `G-VERIFY-AIRTIGHT` | ✅完全 | 气密与泄漏测试 |
| 组装工艺 | `G-PROD-ASSEMBLY` | ✅完全 | 装配工艺 |
| 包装/POP | `G-PROD-PACK` | ✅完全 | 包装工艺 |
| 特殊特性清单 | `G-DEV-PPAP` | 🟡部分 | PPAP内含特殊特性，无独立节点 |

## TH · 热管理（3）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 热仿真（功耗+水道） | `G-VERIFY-CAE-THERMAL;G-METHOD-CAE-THERMAL` | ✅完全 | 热仿真验证+方法 |
| 散热设计（散热器/水道/风冷） | `P-HW-THERMAL` | ✅完全 | 散热器/导热/风冷 |
| 热测试 | `G-VERIFY-THERMAL` | ✅完全 | 热测试（温升/热循环/热冲击） |

## EMC · EMC/安规（3）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| EMC设计（滤波/屏蔽/接地） | `R-EMC;P-HW-OBC-EMI;P-HW-MECH-SHIELD` | ✅完全 | EMC需求+EMI滤波+屏蔽防护 |
| EMC测试（传导/辐射/抗扰） | `GAP` | ❌缺口 | 无EMC测试节点(G-VERIFY-ELECTRICAL是安规非EMC) |
| 安规检查（间隙/爬电/耐压） | `R-SAFETY` | ✅完全 | 电气安全需求 |

## FUSA · 功能安全（7）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 相关项定义 item definition | `GAP` | ❌缺口 | 无相关项定义节点 |
| 危害分析与风险评估 HARA | `GAP` | ❌缺口 | 无HARA节点 |
| 功能安全概念 FSC | `R-FSC` | 🟡部分 | 功能安全需求含SG/FSR/TSR，无独立概念节点 |
| 技术安全概念 TSC | `GAP` | ❌缺口 | 无技术安全概念节点 |
| 硬件安全指标（PMHF/SPFM/LFM） | `GAP` | ❌缺口 | 无硬件安全指标节点 |
| 安全验证与确认 | `GAP` | ❌缺口 | 无安全验证节点 |
| 安全案例 safety case | `GAP` | ❌缺口 | 无安全案例节点 |

## REL · 可靠性（5）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 可靠性目标与分配 | `R-REL` | ✅完全 | 可靠性需求（耐久/寿命/噪声） |
| 可靠性预计 | `GAP` | ❌缺口 | 无可靠性预计节点 |
| 加速寿命试验 ALT | `G-VERIFY-REL` | 🟡部分 | 可靠性试验含耐久/老化，无独立ALT |
| 失效分析 FA | `Q-PROBLEM-FAILURE` | ✅完全 | 失效分析（失效/断裂/开裂/破损） |
| 降额设计 | `P-CAL;R-PERF` | ✅完全 | 降额曲线 + 性能需求(降额) |

## IE · 工艺IE（7）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| 工艺 DFA | `G-METHOD-DFM` | ✅完全 | DFM/DFA设计方法 |
| DFM | `G-METHOD-DFM` | ✅完全 | 同上 |
| PCBA 组装工艺 | `G-PROD` | 🟡部分 | 生产过程树含PCBA，无独立节点 |
| 产品组装工艺 | `G-PROD-ASSEMBLY` | ✅完全 | 装配工艺 |
| 产品过程流程图 PFD | `G-PROD` | 🟡部分 | 生产过程树，无独立PFD节点 |
| 控制计划 Control Plan | `G-DEV-PPAP` | 🟡部分 | PPAP内含控制计划 |
| PFMEA | `Q-FAILURE` | 🟡部分 | FMEA通用节点，无独立PFMEA |

## TE · 测试TE（7）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| DV/PV 测试计划 | `G-DEV` | 🟡部分 | 开发阶段(EVT/PT/PPAP)，无独立测试计划节点 |
| 样机验证 | `G-DEV-EVT1;G-DEV-EVT2` | 🟡部分 | EVT1/EVT2阶段 |
| 出厂测试 | `G-PROD` | 🟡部分 | 生产过程树含生产测试 |
| 气密测试 | `G-VERIFY-AIRTIGHT` | ✅完全 | 气密与泄漏测试 |
| 力学试验（冲击/振动/扫频） | `G-VERIFY-VIBRATION` | ✅完全 | 振动与冲击测试 |
| 环境测试（高低温/湿热/盐雾） | `G-VERIFY-ENV` | ✅完全 | 环境测试 |
| 电气性能测试（效率/纹波/限流/过冲） | `GAP` | ❌缺口 | G-VERIFY-ELECTRICAL是耐压/绝缘/安规，无性能测试节点 |

## QA · 质量（8）

| 工作包 | 骨架节点 | 覆盖 | 说明 |
|---|---|---|---|
| DQA 设计质量保证 | `GAP` | ❌缺口 | 无DQA节点 |
| AQE 先期质量 | `GAP` | ❌缺口 | 无AQE节点 |
| DFMEA/PFMEA | `Q-FAILURE` | ✅完全 | 失效模式（FMEA相关） |
| 8D 问题解决 | `GAP` | ❌缺口 | 无8D节点(Q-PROBLEM是问题记录非8D方法) |
| Issuelog/质量问题清单 | `Q-PROBLEM` | ✅完全 | 问题记录（问题排查/踩坑记录） |
| PPAP 生产件批准 | `G-DEV-PPAP` | ✅完全 | PPAP（量产批准） |
| SPC 统计过程控制 | `GAP` | ❌缺口 | 无SPC节点 |
| MSA 测量系统分析 | `GAP` | ❌缺口 | 无MSA节点 |
