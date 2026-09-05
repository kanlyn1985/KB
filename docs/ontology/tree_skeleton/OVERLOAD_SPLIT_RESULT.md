# 过载节点细分结果（2026-08-18）

> 骨架：`skeleton_v0.4.json`（tree_version 0.4.0，210 节点 = 177 + 33 子节点）
> 落位：`llm_landing/merged_full_records_v04.jsonl`（303,981 条）
> 细分任务：`llm_landing/reland_split/split_records.jsonl`（109,924 条重新落位，95.7% 归属）

## 结果总览

| 指标 | 细分前（v0.3） | 细分后（v0.4） |
|---|---|---|
| 骨架节点 | 177 | 210（+33） |
| 总落位条数 | 303,981 | 303,981 |
| 归属率 | 82.1% | 80.9%（细分任务 4,721 条进复核） |
| 空节点 | 1 | 1（F-DCDC） |
| 过载节点（>5000） | 9 | 7 |

## 8 个过载节点族细分后分布

| 节点族 | 原条数 | 子节点分布（前5） |
|---|---|---|
| G-METHOD-AUTOSAR | 30,510 | STD 21,186 / 父 3,289 / CODEGEN 2,283 / CFG 1,862 / COMM 903 |
| G-PROD-ASSEMBLY | 27,656 | GEN 17,628 / FASTEN 9,893 / 父 1,615 / FIXTURE 1,212 / BOND 1,052 |
| G-PROD-POTTING | 13,758 | DISP 5,772 / POT 4,289 / THERMAL 3,760 / 父 1,553 / SEAL 1,139 |
| G-VERIFY-CAE | 9,843 | STRUCT 6,036 / THERMAL 4,338 / VIBRATION 2,492 / FLUID 1,246 / 父 511 |
| Q-PROBLEM | 8,429 | 父 5,460 / DEFECT 2,241 / FAILURE 1,190 / TEST 544 / CUSTOMER 482 |
| G-METHOD-CAE-STRUCT | 8,397 | 父 2,956 / STRENGTH 1,960 / MODAL 1,668 / TOOL 440 |
| P-SW-BSW | 6,148 | COMM 2,084 / 父 1,691 / MCAL 469 / DIAG 415 / MEM 308 |
| G-VERIFY-VIBRATION | 5,183 | VIB 1,718 / SHOCK 877 / COND 674 / 父 644 |

> 注：部分节点族合计含少量落入复核的条目，故子节点之和略小于原条数。

## 残留过载节点（7 个，>5000）

细分后仍有 7 个节点 >5000 条，但其中 5 个是**新子节点**（STD/GEN/FASTEN/CAE-STRUCT/DISP），
说明这些子节点命名过宽或内容确实高度集中：

| 节点 | 条数 | 备注 |
|---|---|---|
| G-METHOD-AUTOSAR-STD | 21,186 | AUTOSAR 规范条款——内容量大，可再按规范文档细分 |
| G-PROD-ASSEMBLY-GEN | 17,628 | 通用组装——LLM 默认落位点，可接受 |
| G-PROD-ASSEMBLY-FASTEN | 9,893 | 螺纹紧固——内容量大 |
| G-DEV | 6,820 | 开发过程（已有 8 子节点，父节点承接通用内容） |
| G-VERIFY-CAE-STRUCT | 6,036 | 结构仿真验证 |
| G-PROD-POTTING-DISP | 5,772 | 点胶涂覆 |
| Q-PROBLEM | 5,460 | 问题记录（父节点仍承接大量通用问题内容） |

## 结论

1. 细分基本成功：9 个过载节点中 **2 个完全解决**（G-METHOD-CAE-STRUCT、G-VERIFY-VIBRATION 降至 <5000），
   其余 7 个从"单点过载"变为"分布到子节点"，最大单点从 30,510 → 21,186
2. 新子节点中 5 个自身过载——命名偏宽（如 -GEN 通用类、-STD 规范条款），
   若需进一步细分可再迭代一轮
3. 归属率 80.9%（细分任务 4,721 条因低置信度/无匹配进复核，属正常）
4. 空节点维持 1 个（F-DCDC，需人工确认）→ **2026-08-18 已确认：非真空**
   - F-DCDC 父节点 0 条是"最具体优先"落位规则下的正常现象（F-OBC 父节点也仅 5 条）
   - F-DCDC 子树（CONV/REVERSE/PROTECT）有 **44 条真实内容**（反向预充/12V 低压/快充回路）
   - DCDC 相关内容（1,820 条）多数落在 P-SW-ASW-DCDC* 软件组件节点——物理/逻辑层优先于功能层，
     符合落位偏好，非数据缺失
   - **结论：F-DCDC 无需处理，全部 210 节点均有效**

## 交付物

- `skeleton_v0.4.json`（210 节点，tree_version 0.4.0）
- `skeleton_v0.4.xlsx`（骨架结构 Excel）
- `skeleton_v0.4_landing.xlsx`（210 节点 × 落位统计）
- `llm_landing/merged_full_records_v04.jsonl`（303,981 条最终落位）
- `llm_landing/reland_split/`（细分任务产物：records/review/state）
- `OVERLOAD_SPLIT_PLAN.md`（细分方案）
- `split_overload.py`（细分脚本）
