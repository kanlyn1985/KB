# 过载节点细分方案（2026-08-18）

> 数据源：`llm_landing/merged_full_records.jsonl`（303,981 条合并落位）
> 原则：拆分基于落位内容的主题聚类；子节点 ID 遵循 `父ID-XX` 命名；
> 仅拆分 >5000 条的叶子节点；G-DEV 已有 8 个阶段子节点不再重复拆分。

## 细分明细

### 1. G-METHOD-AUTOSAR（30,510 条 → 拆 6 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| G-METHOD-AUTOSAR-COMM | AUTOSAR 通信与诊断（COM/DCM/DEM/CAN/LIN/ETH） | ~8,401 | 通信/诊断 28% |
| G-METHOD-AUTOSAR-OS | AUTOSAR OS/内存（OS/NVM/Flash/EEPROM） | ~4,956 | OS/内存 16% |
| G-METHOD-AUTOSAR-RTE | RTE 与接口（RTE/Port/接口映射） | ~3,031 | RTE/接口 10% |
| G-METHOD-AUTOSAR-CFG | ECU 配置（Neusar/EB/配置工具） | ~2,510 | ECU配置 8% |
| G-METHOD-AUTOSAR-STD | AUTOSAR 规范条款（ARXML/标准文档） | ~2,087 | AUTOSAR规范 7% |
| G-METHOD-AUTOSAR-CODEGEN | 代码生成（C-Code/生成规则） | ~102 | 代码生成 0.3% |

### 2. G-PROD-ASSEMBLY（27,656 条 → 拆 5 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| G-PROD-ASSEMBLY-FASTEN | 螺纹紧固（螺钉/螺栓/扭矩/预紧） | ~1,990 | 螺纹紧固 7% |
| G-PROD-ASSEMBLY-PRESS | 压装压接（压装/压接/压入） | ~119 | 压装 0.4% |
| G-PROD-ASSEMBLY-BOND | 涂胶密封（涂胶/密封/点胶） | ~1,093 | 涂胶 4% |
| G-PROD-ASSEMBLY-FIXTURE | 工装治具（工装/治具/夹具） | ~1,178 | 工装 4% |
| G-PROD-ASSEMBLY-GEN | 通用组装（组装/装配/安装/插接） | ~12,403 | 组装 45% |

### 3. G-PROD-POTTING（13,758 条 → 拆 4 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| G-PROD-POTTING-POT | 灌封（灌封/灌胶/灌封胶） | ~2,517 | 灌封 18% |
| G-PROD-POTTING-DISP | 点胶涂覆（点胶/涂覆/三防） | ~5,412 | 点胶 39% |
| G-PROD-POTTING-THERMAL | 导热材料（导热胶/导热泥/导热硅） | ~1,394 | 导热 10% |
| G-PROD-POTTING-SEAL | 密封胶（密封胶/FIPG/CIPG） | ~444 | 密封 3% |

### 4. G-VERIFY-CAE（9,843 条 → 拆 4 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| G-VERIFY-CAE-THERMAL | 热仿真验证（热仿真/热阻/温升） | ~1,335 | 热仿真 14% |
| G-VERIFY-CAE-STRUCT | 结构仿真验证（应力/强度/静力学） | ~1,400 | 结构 14% |
| G-VERIFY-CAE-VIBRATION | 振动仿真验证（振动/模态） | ~1,160 | 振动 12% |
| G-VERIFY-CAE-FLUID | 流阻流体（流阻/CFD/流道） | ~55 | 流阻 1% |

### 5. Q-PROBLEM（8,429 条 → 拆 4 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| Q-PROBLEM-FAILURE | 失效分析（失效/断裂/开裂/破损） | ~412 | 失效 5% |
| Q-PROBLEM-CUSTOMER | 客诉与问题（客诉/投诉/异常） | ~3,753 | 客诉 45% |
| Q-PROBLEM-DEFECT | 工艺缺陷（缺陷/气泡/溢胶/氧化） | ~221 | 缺陷 3% |
| Q-PROBLEM-TEST | 测试异常（不合格/超差/NG） | ~231 | 测试 3% |

### 6. G-METHOD-CAE-STRUCT（8,397 条 → 拆 3 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| G-METHOD-CAE-STRUCT-STRENGTH | 强度疲劳（强度/应力/疲劳/静力学） | ~686 | 强度 8% |
| G-METHOD-CAE-STRUCT-MODAL | 模态分析（模态/固有频率） | ~965 | 模态 11% |
| G-METHOD-CAE-STRUCT-TOOL | 仿真工具方法（ANSYS/CAE/FLOEFD） | ~875 | 工具 10% |

### 7. G-DEV（7,151 条）— 不拆

已有 8 个阶段子节点（RFQ/EVT1/EVT2/ET/PT0/PT1/PPAP/SOP），剩余内容多为
项目管理/文档模板（G-DEV 直接挂载），维持现状。

### 8. P-SW-BSW（6,148 条 → 拆 4 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| P-SW-BSW-COMM | BSW 通信栈（CAN/LIN/ETH/网络管理） | ~1,361 | 通信栈 22% |
| P-SW-BSW-MCAL | MCAL 驱动（ADC/SPI/GPIO/PWM/WDG） | ~202 | MCAL 3% |
| P-SW-BSW-DIAG | BSW 诊断（DCM/DEM/UDS/OBD） | ~194 | 诊断 3% |
| P-SW-BSW-MEM | BSW 存储（NVM/Flash/EEPROM） | ~115 | 存储 2% |

### 9. G-VERIFY-VIBRATION（5,183 条 → 拆 3 个）

| 新节点 | 名称 | 当前条数 | 依据 |
|---|---|---|---|
| G-VERIFY-VIBRATION-VIB | 振动测试（振动/随机/正弦/扫频） | ~1,539 | 振动 30% |
| G-VERIFY-VIBRATION-SHOCK | 冲击跌落（冲击/跌落/Shock） | ~663 | 冲击 13% |
| G-VERIFY-VIBRATION-COND | 试验条件（PSD/GRMS/加速度） | ~176 | 条件 3% |

## 汇总

- 拆分的过载节点：8 个（G-DEV 除外）
- 新增子节点：6+5+4+4+4+3+4+3 = **33 个**
- 骨架节点：177 → **210**
- tree_version：0.3.3 → **0.4.0**

## 执行步骤（确认后）

1. 更新 `skeleton_v0.2.json`：新增 33 个子节点 + 提升 tree_version
2. 导出骨架 Excel（`skeleton_v0.4.xlsx`）
3. 用新骨架重跑落位（或对过载节点内容做二次细分落位）
4. 验证各子节点条数分布
