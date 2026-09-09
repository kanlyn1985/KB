"""节点归属器：内容单元 → 骨架节点（规则 + 白名单校验）。

规则层（确定性）：单元类型 + 关键词 → 节点候选（带置信度）
校验层（代码强制）：候选必须存在于骨架 JSON（白名单）
LLM 层（可选，预留接口）：出候选补充（后续接入）

输出落位记录：
  {unit_id, doc, unit_type, text, node_id|None, confidence, rule, reason}
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.2.json"
UNITS_FILE = ROOT / "docs" / "ontology" / "tree_skeleton" / "units_sample.json"
MANIFEST = ROOT / "docs" / "ontology" / "tree_skeleton" / "doc_manifest.json"


def load_skeleton() -> dict[str, dict]:
    data = json.loads(SKELETON.read_text(encoding="utf-8"))
    return {n["id"]: n for n in data["nodes"]}


def build_index(nodes: dict[str, dict]) -> dict[str, str]:
    """节点名关键词索引：关键词 → 节点ID"""
    idx: dict[str, str] = {}
    for nid, n in nodes.items():
        name = n["name"]
        # 提取节点名中的核心词（括号外部分 + 括号内关键词）
        for kw in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", name):
            if len(kw) >= 2 and kw not in idx:
                idx[kw.lower()] = nid
    return idx


# 策略 → L-STRATEGY 关键词表
STRATEGY_RULES = [
    ("抖频", "L-STRATEGY-FREQ"),
    ("CBC", "L-STRATEGY-CBC"),
    ("峰值功率", "L-STRATEGY-PEAK"),
    ("预充", "L-STRATEGY-PRECHARGE"),
    ("NTC", "L-STRATEGY-NTC"),
    ("低温", "L-STRATEGY-LOWTEMP"),
    ("V2L", "L-STRATEGY-V2L"),
    ("光耦", "L-STRATEGY-OPTO"),
    ("GPIO", "L-STRATEGY-GPIO"),
    ("采样容差", "L-STRATEGY-SENSE"),
    ("采样", "L-SENSE"),
]

# 组件 → P-SW-ASW 关键词表
COMPONENT_RULES = [
    ("CC详细设计", "P-SW-ASW-CC"), ("\\bCC\\b", "P-SW-ASW-CC"),
    ("\\bCP\\b", "P-SW-ASW-CP"), ("CPOUT", "P-SW-ASW-CPOUT"),
    ("ACRelay", "P-SW-ASW-ACRELAY"), ("AuxPower", "P-SW-ASW-AUXPWR"),
    ("CANReport", "P-SW-ASW-CANREPORT"), ("CAN_Receive", "P-SW-ASW-CANRCV"),
    ("Calibration", "P-SW-ASW-CAL"), ("DCDCFault", "P-SW-ASW-DCDCFAULTDET"),
    ("OBCFault", "P-SW-ASW-OBCFAULTDET"), ("ADC", "P-SW-ASW-ADC"),
    ("OBCPowerCtrl", "P-SW-ASW-OBCPWRCTRL"), ("DCDCPowerCtrl", "P-SW-ASW-DCDCPWRCTRL"),
    ("DCDCState", "P-SW-ASW-DCDCSTATE"), ("OBCState", "P-SW-ASW-OBCSTATE"),
    ("INSDET", "P-SW-ASW-INSDET"), ("Interlock", "P-SW-ASW-INTERLOCK"),
    ("ORingOVP", "P-SW-ASW-ORINGOVP"), ("SleepWake", "P-SW-ASW-SLEEPWAKE"),
    ("GunManage", "P-SW-ASW-GUNMANAGE"), ("GunTemp", "P-SW-ASW-GUNTEMP"),
    ("UDManage", "P-SW-ASW-UDMANAGE"), ("Temp", "P-SW-ASW-TEMP"),
    ("DEH", "P-SW-ASW-DEH"), ("ELEclock", "P-SW-ASW-ELECLOCK"),
    ("HVDM", "P-SW-ASW-HVDM"), ("S2", "P-SW-ASW-S2"),
    ("LED", "P-SW-ASW-LED"), ("NACS", "P-SW-ASW-NACS"),
    ("功率控制", "P-SW-ASW-OBCPWRCTRL"), ("采样", "P-SW-ASW-ADC"),
]

# 需求 → R 节点关键词表
REQUIREMENT_RULES = [
    ("性能", "R-PERF"), ("电压", "R-PERF"), ("电流", "R-PERF"), ("效率", "R-PERF"),
    ("保护", "R-PROTECT"), ("安全", "R-SAFETY"), ("EMC", "R-EMC"), ("环境", "R-ENV"),
    ("耐久", "R-REL"), ("软件", "R-SW"), ("硬件", "R-HW"), ("通信", "R-IF"),
    ("接口", "R-IF"), ("功能安全", "R-FSC"), ("诊断", "R-SW"), ("标定", "R-SW"),
]

# 条款 → R-STD
# 经验 → 质量/经验类（骨架待增枝：EXP-ROOT）
# 流程 → G 过程维度
PROCESS_RULES = [
    ("ASPICE", "G-PROC-STD"), ("SYS.", "G-PROC-STD"), ("SWE.", "G-PROC-STD"),
    ("流程", "G-DEV"), ("阶段", "G-DEV"), ("工艺", "G-PROD"), ("试制", "G-PROD"),
]


def rule_match(unit: dict, nodes: dict[str, dict]) -> tuple:
    utype = unit["unit_type"]
    text = unit["text"]
    low = text.lower()
    # 用文件名而非完整路径（避免分类目录关键词污染，如"30_产品平台知识"含"知识"）
    doc_name = str(Path(str(unit.get("doc", ""))).name).lower()

    # 决策A：器件 Datasheet → P 层器件（MCU）
    if "datasheet" in doc_name or "数据手册" in doc_name:
        return "P-HW-CTRL-MCU", "doc:datasheet", 0.8, None

    # 芯片资料（用户手册/数据手册/芯片参考）→ P 层器件
    if any(k in doc_name for k in ("aurix", "tc4", "fs26", "infineon", "_um_", "um_ch", "sitara", "am263")):
        return "P-HW-CTRL-MCU", "doc:chip-ref", 0.8, None

    # 决策B：继电器知识 → AC 继电器节点（文本级）
    if "继电器" in text or "relay" in low:
        if any(k in doc_name for k in ("标准法规", "标准", "法规")):
            return "R-STD", "doc:relay-std", 0.8, None
        if "方案对比" in doc_name or "对比" in doc_name:
            return "Q-LESSON", "doc:relay-compare", 0.7, None
        return "P-HW-OBC-ACRELAY", "para:relay", 0.7, None

    # AC 继电器使用场景（充电/V2L 场景描述）→ AC 继电器节点
    if "ac继电器" in doc_name or "ac relay" in doc_name:
        return "P-HW-OBC-ACRELAY", "doc:relay-scenario", 0.75, None

    # 时序图/驱动时序 → P 驱动电路
    if any(k in doc_name for k in ("时序图", "驱动时序", "gen5驱动")):
        return "P-HW-CTRL-DRV", "doc:timing", 0.8, None

    # 校表功能/校表策略 → 标定组件
    if "校表" in doc_name:
        return "P-SW-ASW-CAL", "doc:calibration", 0.7, None

    # 决策C：知识类文档（简介/原理/知识点）→ 产品知识节点（文档级）
    if any(k in doc_name for k in ("简介", "原理", "知识")):
        if "dcdc" in doc_name:
            return "P-KNOW-DCDC", "doc:know-dcdc", 0.8, None
        return "P-KNOW-OBC", "doc:know-obc", 0.8, None

    # 质量/经验类：问题排查/踩坑/复盘/FAQ → Q 域（8 类实体：质量失效类）
    if any(k in doc_name for k in ("问题", "踩坑", "排查", "调查", "复盘", "FAQ", "故障", "记录",
                                   "fmea", "ppap", "msa", "spc", "apqp", "手册",
                                   "最佳实践", "修改", "不准", "失败", "偶发", "汇报", "learning", "分享")):
        if any(k in doc_name for k in ("复盘", "FAQ", "最佳实践", "经验", "ppap", "msa", "spc", "apqp",
                                       "汇报", "learning", "分享")):
            return "Q-LESSON", "doc:lesson", 0.8, None
        if "fmea" in doc_name or "失效" in doc_name:
            return "Q-FAILURE", "doc:failure", 0.8, None
        return "Q-PROBLEM", "doc:problem", 0.8, None

    # OBCState 命名规则 → 状态组件
    if "namingrules" in doc_name or "命名规则" in doc_name:
        return "P-SW-ASW-OBCSTATE", "doc:naming-rule", 0.8, None

    # 标定需求/标定Flash → 标定组件
    if "标定" in doc_name and ("需求" in doc_name or "flash" in doc_name):
        return "P-SW-ASW-CAL", "doc:cal-req", 0.7, None

    # AUTOSAR 官方规范件（MOD/TR/TP/00046 等规范原文）→ 标准条款树
    if any(k in doc_name for k in ("autosar_mod", "autosar_tr", "autosar_tp", "autosar_00046",
                                   "autosar_sws", "autosar_prs", "standards_4_4_0", "r18-10")):
        return "R-STD", "doc:autosar-spec", 0.85, None

    # EE 文档：公司工程规范/模板/Checklist → G 过程维度 / P 物理层 / R 标准
    # HW_ELxx 硬件电路设计规范 → P 层硬件树（按电路名匹配）
    if "hw_el" in doc_name and "circuit" in doc_name:
        hw_map = [
            ("pfc", "P-HW-OBC-PFC"), ("lc main power", "P-HW-OBC-DCDC"), ("lc&dcdc", "P-HW-OBC-DCDC"),
            ("dcdc primary", "P-HW-DCDC-CONV"), ("dcdc", "P-HW-DCDC"),
            ("emi filter", "P-HW-OBC-EMI"), ("ac emi", "P-HW-OBC-EMI"),
            ("auxiliary", "P-HW-OBC-AUX"), ("mcu", "P-HW-CTRL-MCU"),
            ("sample", "P-HW-CTRL-SENSE"), ("filter", "P-HW-CTRL-SENSE"),
            ("insulation", "P-HW-CTRL-SENSE"), ("cp sample", "P-HW-CTRL-SENSE"),
            ("current samp", "P-HW-CTRL-SENSE"), ("kl30", "P-HW-CTRL-SENSE"),
            ("can communication", "P-HW-CTRL-MCU"), ("elock", "P-HW-OBC-ACRELAY"),
            ("evcc", "P-HW-OBC"), ("nacs", "P-HW-OBC"), ("rcd", "P-HW-CTRL-PROTECT"),
            ("led", "P-HW-MECH"), ("stla", "P-HW-MECH"),
        ]
        for kw, nid in hw_map:
            if kw in doc_name:
                return nid, f"doc:hw-circuit-{kw}", 0.8, None
        return "P-HW", "doc:hw-circuit", 0.7, None

    # 电容应用规范 → P-HW（器件选型）
    if "电容" in doc_name and ("应用" in doc_name or "规范" in doc_name):
        return "P-HW", "doc:capacitor", 0.7, None

    # 产品系统设计方案 → F-ROOT（系统设计）
    if "系统设计方案" in doc_name:
        return "F-ROOT", "doc:system-design", 0.7, None

    # 评审 Checklist / 评审要素表 → G-DEV（开发过程评审活动）
    if any(k in doc_name for k in ("checklist", "评审要素", "评审表", "检查表", "确认清单")):
        return "G-DEV", "doc:review-checklist", 0.8, None

    # 功能安全（FMEA/FTA/FMEDA/HW Safety/Safety Design/HWD）→ R-FSC
    if any(k in doc_name for k in ("dfmea", "fmea", "fta", "fmeda", "safety design",
                                   "hw safety", "hwd", "硬件安全", "功能安全")):
        return "R-FSC", "doc:func-safety", 0.85, None

    # 安规设计 → R-SAFETY
    if "安规" in doc_name:
        return "R-SAFETY", "doc:safety-design", 0.8, None

    # 拓扑设计 → P-HW-OBC-PFC（PFC/拓扑）
    if "拓扑" in doc_name:
        return "P-HW-OBC-PFC", "doc:topology", 0.75, None

    # 主功率设计/功率特性曲线 → P-HW-OBC-DCDC（隔离变换级）
    if "主功率" in doc_name or "功率特性曲线" in doc_name:
        return "P-HW-OBC-DCDC", "doc:power-design", 0.75, None

    # BOM/物料/ECR 变更 → G-DEV（BOM 管理/变更管理）
    if any(k in doc_name for k in ("bom", "物料", "ecr", "变更", "版本管理")):
        if "线束" in doc_name:
            return "P-HW-MECH-HARNESS", "doc:me-harness", 0.8, None
        return "G-DEV", "doc:bom-ecr", 0.75, None

    # 磁件/变压器/电感/绕组 → 磁件学科（提级后的独立学科）
    if any(k in doc_name for k in ("磁件", "变压器", "电感", "绕组", "磁芯", "磁性元件",
                                   "transformer", "inductor", "magnetic")):
        return "P-HW-MAG", "doc:me-magnetic", 0.8, None

    # 热测试/水温拟合/内特性测试/外特性测试 → G-DEV（测试活动）
    if any(k in doc_name for k in ("热测试", "水温", "内特性测试", "外特性测试", "测试流程", "测试规范")):
        return "G-DEV", "doc:test-spec", 0.75, None

    # PCB 规范/流程 → P-HW（硬件 PCB）
    if "pcb" in doc_name:
        return "P-HW", "doc:pcb", 0.7, None

    # 三防涂覆/工艺 → G-PROD（生产过程）
    if "三防" in doc_name or "涂覆" in doc_name:
        return "G-PROD", "doc:process", 0.75, None

    # 采样容差分析 → P-HW-CTRL-SENSE
    if "采样容差" in doc_name or "容差分析" in doc_name:
        return "P-HW-CTRL-SENSE", "doc:tolerance", 0.75, None

    # 管理制度/员工手册/奖惩/培训 → Q-LESSON（管理经验）
    if any(k in doc_name for k in ("奖惩", "员工手册", "管理制度", "管理指引", "管理规范", "培训")):
        return "Q-LESSON", "doc:mgmt", 0.7, None

    # 流程规范/标准化 → G-DEV（流程标准）
    if "流程" in doc_name or "标准化" in doc_name:
        return "G-DEV", "doc:process-std", 0.7, None

    # 原理图规范 → P-HW（硬件设计）
    if "原理图" in doc_name:
        return "P-HW", "doc:schematic", 0.7, None

    # 损耗分布图 → P-HW-MAG（磁件损耗）
    if "损耗" in doc_name:
        return "P-HW-MAG", "doc:mag-loss", 0.7, None

    # 标定/校表 → P-SW-ASW-CAL
    if "校表" in doc_name or "标定" in doc_name:
        return "P-SW-ASW-CAL", "doc:calibration", 0.7, None

    # 充电引导接口测试 → G-DEV
    if "充电引导" in doc_name or "接口电路测试" in doc_name:
        return "G-DEV", "doc:interface-test", 0.75, None
    if any(k in doc_name for k in ("代码资产", "文档模板", "cbb", "标准化cbb")):
        return "G-ASSET", "doc:asset", 0.8, None

    # SW4 标准策略族（文档级：SW4_<组件>标准策略 → P-SW-ASW-<组件>）
    if "标准策略" in doc_name or "标准化策略" in doc_name or "sw4_" in doc_name:
        sw4_map = [
            ("obcpowerctrl", "P-SW-ASW-OBCPWRCTRL"), ("dcdcpowerctrl", "P-SW-ASW-DCDCPWRCTRL"),
            ("adcsignal", "P-SW-ASW-ADC"), ("auxpwr", "P-SW-ASW-AUXPWR"),
            ("canreceive", "P-SW-ASW-CANRCV"), ("dcdcfault", "P-SW-ASW-DCDCFAULTDET"),
            ("obcfault", "P-SW-ASW-OBCFAULTDET"), ("obcflt", "P-SW-ASW-OBCFAULTDET"),
            ("dcdcflt", "P-SW-ASW-DCDCFAULTDET"),
            ("gunmanage", "P-SW-ASW-GUNMANAGE"), ("guntemp", "P-SW-ASW-GUNTEMP"),
            ("insdet", "P-SW-ASW-INSDET"), ("oringovp", "P-SW-ASW-ORINGOVP"),
            ("lvbat", "P-SW-ASW-AUXPWR"), ("dcdcsts", "P-SW-ASW-DCDCSTATE"),
            ("obcsts", "P-SW-ASW-OBCSTATE"), ("hv", "P-SW-ASW-INTERLOCK"),
            ("sleepwake", "P-SW-ASW-SLEEPWAKE"), ("temp", "P-SW-ASW-TEMP"),
            ("udmanage", "P-SW-ASW-UDMANAGE"), ("interlock", "P-SW-ASW-INTERLOCK"),
            ("s2", "P-SW-ASW-S2"), ("led", "P-SW-ASW-LED"), ("nacs", "P-SW-ASW-NACS"),
            ("deh", "P-SW-ASW-DEH"), ("eleclock", "P-SW-ASW-ELECLOCK"),
            ("hvdm", "P-SW-ASW-HVDM"), ("cpo", "P-SW-ASW-CPOUT"),
            ("cc", "P-SW-ASW-CC"), ("cp", "P-SW-ASW-CP"),
        ]
        for kw, nid in sw4_map:
            if kw in doc_name:
                return nid, f"doc:sw4-{kw}", 0.85, None
        return "P-SW-ASW", "doc:sw4-default", 0.6, None

    # 编码规范/通用设计规范 → R-STD
    if any(k in doc_name for k in ("coding specification", "通用设计规范", "c coding", "hzevt",
                                   "安全规范", "模板规范", "规范摘要", "命名规范", "ai规范",
                                   "规范总览")):
        return "R-STD", "doc:coding-std", 0.85, None

    # 可复用代码模式库 → G-ASSET
    if "代码模式" in doc_name or "可复用代码" in doc_name:
        return "G-ASSET", "doc:code-pattern", 0.8, None

    # 函数架构/代码打包规范 → P-SW-ASW
    if "函数架构" in doc_name or "代码打包" in doc_name:
        return "P-SW-ASW", "doc:code-arch", 0.75, None

    # ISO9001/质量体系完整版 → R-STD
    if "iso9001" in doc_name or "iso 9001" in doc_name or "iso9000" in doc_name:
        return "R-STD", "doc:iso9001", 0.85, None

    # SN 29500 元器件失效率 → R-STD
    if "sn 29500" in doc_name or "元器件失效" in doc_name:
        return "R-STD", "doc:reliability-std", 0.85, None

    # Arxml 示例/组件 Arxml → R-STD
    if "arxml" in doc_name and ("示例" in doc_name or "组件" in doc_name):
        return "R-STD", "doc:arxml-example", 0.8, None

    # G5↔SW4 模块映射 → P-SW-ASW
    if "g5↔sw4" in doc_name or "模块映射" in doc_name:
        return "P-SW-ASW", "doc:module-map", 0.75, None

    # 软件性能提升 → L 层
    if "软件性能" in doc_name or "性能提升方法" in doc_name:
        return "L-ROOT", "doc:perf-method", 0.7, None

    # 文档导入标准作业程序 → G-METHOD-TOOL
    if "文档导入" in doc_name and "标准作业" in doc_name:
        return "G-METHOD-TOOL", "doc:import-sop", 0.8, None

    # 充放电流程介绍 → F 功能
    if "充放电流程" in doc_name:
        return "F-OBC-CHARGE", "doc:charge-flow", 0.75, None

    # DBC 报文/CAN 信号 → R-IF
    if "dbc" in doc_name or ("can" in doc_name and "报文" in doc_name):
        return "R-IF", "doc:dbc", 0.8, None

    # E-Gas/GB T 41578/其他英文标准 → R-STD
    if any(k in doc_name for k in ("e-gas", "e gas", "gas monitoring", "gb t 41578",
                                   "gb t 18487", "din spec")):
        return "R-STD", "doc:std-eng", 0.85, None

    # 代码模板/头文件模板/源文件示例/存储类包模板 → G-ASSET
    if any(k in doc_name for k in ("头文件模板", "源文件示例", "模板", "存储类包")):
        return "G-ASSET", "doc:code-template", 0.8, None

    # 效率计算/算法策略优化 → L 策略
    if any(k in doc_name for k in ("效率计算", "算法策略", "策略优化")):
        return "L-STRATEGY", "doc:algo-strategy", 0.8, None

    # OBC 状态机需求解析 → 状态组件
    if "状态机需求" in doc_name or "状态机解析" in doc_name:
        return "P-SW-ASW-OBCSTATE", "doc:state-req", 0.8, None

    # 充电连接控制时序 → 驱动电路
    if "充电连接" in doc_name and "时序" in doc_name:
        return "P-HW-CTRL-DRV", "doc:charge-timing", 0.75, None

    # 功能模块设计 → P-SW-ASW（软件架构）
    if "功能模块设计" in doc_name:
        return "P-SW-ASW", "doc:func-module", 0.75, None

    # OBCState 详细设计 → 状态组件
    if "obcstate" in doc_name and "详细设计" in doc_name:
        return "P-SW-ASW-OBCSTATE", "doc:obcstate-spec", 0.85, None

    # 标定/测量工具规范与手册（ASAM XCP/ASAP2/ETAS INCA）→ G-METHOD-TOOL
    if any(k in doc_name for k in ("asam_xcp", "asap2", "etas", "inca", "es582")):
        return "G-METHOD-TOOL", "doc:cal-tool", 0.85, None

    # 法规/标准（VDA6/IATF/SAE/IEC/UN R/ISOIEC/GBT/NBT/rfc/SHE/SN29500）→ R-STD
    if any(k in doc_name for k in ("vda6", "iatf", "sae_", "sae ", "iec", "isoiec", "un regulation",
                                   "rfc", "she functional", "sn29500", "iec62380", "gbt", "nbt", "gb_t",
                                   "gb/t", "qc_t", "qc/t", "iso ", "iso_15765", "iso_14229",
                                   "iso_11898", "iso 26262", "iso_dis", "iso 15765", "iso 14229",
                                   "iso 11898", "misra", "编码规范",
                                   "iso15118", "gb 18352", "gb 18384", "din spec", "ece r",
                                   "iso9004", "nist", "fips", "iso 9004")):
        return "R-STD", "doc:std-other", 0.85, None

    # 头文件/源文件（Compiler.h/Platform_Types.h/ProjectCfg.h/systemdefine.c）→ P-SW-BSW 基础软件
    if re.search(r"(compiler|platform_types|projectcfg|systemdefine)", doc_name) or doc_name.endswith((".h.md", ".c.md")):
        return "P-SW-BSW", "doc:header-file", 0.8, None

    # 工具/脚本/配置/烧录教程 → G-METHOD-TOOL（工具使用方法）
    if any(k in doc_name for k in ("evtech_tool", "便捷工具", "脚本", "自动化工具",
                                   "hightec", "烧录", "编译器", "总线数据字典",
                                   "code-generator", "code_generator", "autocodeagent",
                                   "arxml-interface", "interface-generator", "skill_spec",
                                   "matlab-python", "联动")):
        return "G-METHOD-TOOL", "doc:tool", 0.8, None

    # ========== ME 结构知识（结构部知识库，v0.3.2 夯实） ==========
    # 结构设计报告/装配说明书 → 结构件
    if any(k in doc_name for k in ("结构设计报告", "结构设计说明书", "装配说明书", "装配作业指导",
                                   "assembly instruction", "结构设计规范", "结构件设计",
                                   "机械设计", "结构开发", "数模评审")):
        return "P-HW-MECH", "doc:me-structure", 0.8, None
    # 壳体/压铸/钣金 → 壳体
    if any(k in doc_name for k in ("壳体", "压铸", "钣金", "机加工", "加工工艺", "铝壳",
                                   "housing", "die cast", "die-cast", "sheet metal")):
        return "P-HW-MECH-HOUSING", "doc:me-housing", 0.8, None
    # 水道/水冷/液冷 → 水道系统
    if any(k in doc_name for k in ("水道", "水冷", "液冷", "水嘴", "水接头", "流道",
                                   "waterway", "water jacket", "liquid cooling", "coolant")):
        return "P-HW-MECH-WATERWAY", "doc:me-waterway", 0.8, None
    # 密封/气密/O型圈 → 密封系统
    if any(k in doc_name for k in ("密封", "气密", "o型圈", "o-ring", "o ring", "密封圈",
                                   "密封垫", "密封胶", "气密测试", "气密性")):
        return "P-HW-MECH-SEAL", "doc:me-seal", 0.8, None
    # 紧固件/螺钉/螺栓 → 紧固件
    if any(k in doc_name for k in ("螺钉", "螺栓", "螺母", "螺柱", "紧固", "卡扣", "螺丝",
                                   "screw", "bolt", "fastener", "thread")):
        return "P-HW-MECH-FASTENER", "doc:me-fastener", 0.8, None
    # 连接器/接插件/端子 → 连接器
    if any(k in doc_name for k in ("连接器", "接插件", "端子", "插件", "connector", "plug",
                                   "socket", "pin")):
        return "P-HW-MECH-CONNECTOR", "doc:me-connector", 0.8, None
    # 铜排/母排 → 铜排
    if any(k in doc_name for k in ("铜排", "母排", "busbar", "bus bar", "铜连接")):
        return "P-HW-MECH-BUSBAR", "doc:me-busbar", 0.8, None
    # 铭牌/标签/标识 → 铭牌
    if any(k in doc_name for k in ("铭牌", "标签", "标识", "nameplate", "label", "打标",
                                   "镭雕", "激光打标")):
        return "P-HW-MECH-NAMEPLATE", "doc:me-nameplate", 0.8, None
    # 屏蔽罩/EMC结构 → 屏蔽
    if any(k in doc_name for k in ("屏蔽罩", "屏蔽", "emi屏蔽", "电磁屏蔽", "shield")):
        return "P-HW-MECH-SHIELD", "doc:me-shield", 0.75, None
    # 支架/托架/安装 → 支架
    if any(k in doc_name for k in ("支架", "托架", "安装板", "安装结构", "法兰", "减震",
                                   "bracket", "mounting")):
        return "P-HW-MECH-BRACKET", "doc:me-bracket", 0.75, None
    # 散热器/散热/导热 → 热管理系统
    if any(k in doc_name for k in ("散热器", "散热", "导热垫", "导热硅脂", "导热泥", "相变材料",
                                   "tim", "thermal pad", "heatsink", "heat sink", "冷却")):
        if any(k in doc_name for k in ("导热垫", "导热硅脂", "导热泥", "相变", "tim", "thermal pad")):
            return "P-HW-THERMAL-TIM", "doc:me-tim", 0.8, None
        if "风扇" in doc_name or "风冷" in doc_name or "fan" in doc_name:
            return "P-HW-THERMAL-FAN", "doc:me-fan", 0.8, None
        return "P-HW-THERMAL-HEATSINK", "doc:me-heatsink", 0.8, None
    # 灌封/涂覆/点胶/三防 → 灌封涂覆
    if any(k in doc_name for k in ("灌封", "灌胶", "点胶", "涂覆", "三防", "粘接剂", "粘接胶",
                                   "potting", "conformal", "adhesive")):
        return "P-HW-THERMAL-POT", "doc:me-potting", 0.8, None
    # 材料 → 材料库
    if any(k in doc_name for k in ("材料", "材质", "选材", "材料性能", "material", "adc12",
                                   "6061", "钕铁硼", "磁钢")):
        return "P-HW-MATERIAL", "doc:me-material", 0.75, None
    if any(k in doc_name for k in ("塑料", "尼龙", "pa66", "ppa", "pbt", "玻纤", "注塑材料")):
        return "P-HW-MATERIAL-PLASTIC", "doc:me-plastic", 0.8, None
    if any(k in doc_name for k in ("橡胶", "硅胶", "弹性体", "rubber", "silicone")):
        return "P-HW-MATERIAL-RUBBER", "doc:me-rubber", 0.8, None
    # 表面处理（阳极/电镀/钝化/喷粉）→ 表面处理
    if any(k in doc_name for k in ("阳极", "电镀", "钝化", "喷粉", "喷涂", "表面处理",
                                   "anodize", "plating", "chromate", "powder coat")):
        return "P-HW-MATERIAL-SURFACE", "doc:me-surface", 0.8, None
    # 公差/尺寸/GD&T → 公差分析方法
    if any(k in doc_name for k in ("公差", "尺寸链", "gd&t", "形位公差", "tolerance",
                                   "全尺寸", "cpk", "三坐标", "检具", "尺寸检测")):
        return "G-METHOD-TOL", "doc:me-tolerance", 0.8, None
    # CAE/仿真 → 仿真方法
    if any(k in doc_name for k in ("热仿真", "cae", "仿真", "flotherm", "cfd", "模态分析",
                                   "流阻", "热阻网络", "simulation")):
        if "热" in doc_name and ("仿真" in doc_name or "simulation" in doc_name):
            return "G-METHOD-CAE-THERMAL", "doc:me-cae-thermal", 0.85, None
        if "模态" in doc_name or "强度" in doc_name or "疲劳" in doc_name or "结构仿真" in doc_name:
            return "G-METHOD-CAE-STRUCT", "doc:me-cae-struct", 0.85, None
        if "流阻" in doc_name or "流道" in doc_name or "风道" in doc_name:
            return "G-METHOD-CAE-FLUID", "doc:me-cae-fluid", 0.85, None
        return "G-METHOD-CAE", "doc:me-cae", 0.8, None
    # DFM/DFA → 制造性设计方法
    if any(k in doc_name for k in ("dfm", "dfa", "可制造性", "可装配性", "装配设计")):
        return "G-METHOD-DFM", "doc:me-dfm", 0.85, None
    # 验证测试（振动/盐雾/环境/可靠性）→ 验证活动树
    if any(k in doc_name for k in ("振动", "冲击", "跌落", "扫频", "vibration", "shock")):
        return "G-VERIFY-VIBRATION", "doc:me-vibration", 0.85, None
    if any(k in doc_name for k in ("盐雾", "湿热", "高低温", "高温", "低温", "环境试验",
                                   "防尘", "ip防护", "environmental")):
        return "G-VERIFY-ENV", "doc:me-env", 0.85, None
    if any(k in doc_name for k in ("气密", "保压", "氦检", "水检", "泄漏")):
        return "G-VERIFY-AIRTIGHT", "doc:me-airtight", 0.85, None
    if any(k in doc_name for k in ("可靠性", "寿命", "老化", "温循", "耐久", "reliability")):
        return "G-VERIFY-REL", "doc:me-reliability", 0.85, None
    if any(k in doc_name for k in ("耐压", "绝缘", "接触电阻", "安规测试", "耐压测试")):
        return "G-VERIFY-ELECTRICAL", "doc:me-electrical-test", 0.8, None
    # 工艺（压铸/机加/注塑/焊接/装配）→ 生产过程
    if any(k in doc_name for k in ("压铸工艺", "压铸参数", "模具", "浇道", "die casting process")):
        return "G-PROD-CASTING", "doc:me-casting", 0.8, None
    if any(k in doc_name for k in ("机加工", "cnc", "钻孔", "攻丝", "铣削", "车削")):
        return "G-PROD-MACHINING", "doc:me-machining", 0.8, None
    if any(k in doc_name for k in ("冲压", "折弯", "焊接", "铆接", "钣金工艺")):
        return "G-PROD-SHEET", "doc:me-sheet", 0.8, None
    if any(k in doc_name for k in ("注塑", "注塑参数", "脱模", "injection mold")):
        return "G-PROD-INJECTION", "doc:me-injection", 0.8, None
    if any(k in doc_name for k in ("压装", "螺纹紧固", "涂胶", "组装", "装配工艺", "装配过程",
                                   "装配作业")):
        return "G-PROD-ASSEMBLY", "doc:me-assembly", 0.8, None
    if any(k in doc_name for k in ("包装", "周转", "防静电", "防护包装", "packaging")):
        return "G-PROD-PACK", "doc:me-pack", 0.8, None
    # 结构评审/DFMEA 结构 → 过程（若含结构关键词按上述规则先命中，兜底到 G-PROD）
    if any(k in doc_name for k in ("结构评审", "结构检查", "结构设计评审", "mechanical design review",
                                   "结构清单", "结构件清单")):
        return "G-PROD", "doc:me-review", 0.7, None
    # 结构部培训/知识/经验 → Q-LESSON
    if any(k in doc_name for k in ("结构知识", "结构培训", "结构分享", "结构学习", "技能培训")):
        return "Q-LESSON", "doc:me-lesson", 0.75, None
    # 供应商/来料/PPAP 结构 → Q-LESSON（供应商质量）
    if any(k in doc_name for k in ("供应商", "来料", "sqe", "supplier", "供方")):
        return "Q-LESSON", "doc:me-supplier", 0.75, None
    # 结构质量问题/客诉 → Q-PROBLEM
    if any(k in doc_name for k in ("结构问题", "结构失效", "客诉", "投诉", "问题分析",
                                   "失效分析", "断裂", "开裂")):
        return "Q-PROBLEM", "doc:me-problem", 0.8, None

    # 软件架构知识 → P-SW-ASW（软件架构/设计）
    if any(k in doc_name for k in ("软件架构", "架构设计", "组件架构")):
        return "P-SW-ASW", "doc:sw-arch", 0.8, None

    # 技术方案对比/选型 → Q-LESSON（经验知识）
    if any(k in doc_name for k in ("技术方案对比", "选型", "培训材料", "容差表", "通讯端口")):
        return "Q-LESSON", "doc:lesson-tool", 0.7, None

    # 参数调研（阻值范围等）→ P 层采样电路参数
    if "调研" in doc_name and ("阻值" in doc_name or "参数" in doc_name):
        return "P-HW-CTRL-SENSE", "doc:param-survey", 0.7, None

    # 项目需求管理 → 开发过程
    if "需求管理" in doc_name:
        return "G-DEV", "doc:req-mgmt", 0.7, None

    # 开发方法论 → G-METHOD 开发方法域（文档级：建模/配置/工具教程）
    if "aspice" in doc_name or "spice" in doc_name:
        return "G-PROC-STD", "doc:aspice", 0.9, None
    if any(k in doc_name for k in ("simulink", "stateflow", "mil", "模型", "建模", "rte",
                                   "neusar", "autosar", "eb", "lld", "代码生成", "mcp",
                                   "polarion", "gitlab", "测试", "e2e", "btc")):
        if any(k in doc_name for k in ("autosar", "rte", "neusar", "eb", "代码生成")):
            return "G-METHOD-AUTOSAR", "doc:method-autosar", 0.8, None
        if any(k in doc_name for k in ("simulink", "stateflow", "mil", "模型", "建模", "lld")):
            return "G-METHOD-MBD", "doc:method-mbd", 0.8, None
        return "G-METHOD-TOOL", "doc:method-tool", 0.8, None

    if utype == "strategy":
        for kw, nid in STRATEGY_RULES:
            if re.search(kw, text, re.IGNORECASE):
                return nid, f"strategy:{kw}", 0.8
        return "L-STRATEGY", "strategy:default", 0.5

    if utype == "component":
        for kw, nid in COMPONENT_RULES:
            if re.search(kw, text, re.IGNORECASE):
                return nid, f"component:{kw}", 0.85
        return "P-SW-ASW", "component:default", 0.5

    if utype == "requirement":
        # 优先用 Title 列（需求表格式：ID | 类型 | Title | 描述 | …）
        parts = text.split(" | ")
        title = parts[2] if len(parts) >= 3 else text
        for kw, nid in REQUIREMENT_RULES:
            if kw in title:
                return nid, f"requirement-title:{kw}", 0.85
        for kw, nid in REQUIREMENT_RULES:
            if kw in text:
                return nid, f"requirement:{kw}", 0.7
        return "R-ROOT", "requirement:default", 0.4

    if utype == "signal":
        # CAN 矩阵/信号定义 → 接口与通信需求（R 层）或 P 层信号（挂软件）
        return "R-IF", "signal:can-matrix", 0.6

    if utype == "fault":
        # 故障列表（触发/动作/恢复）→ L 层故障管理
        return "L-FAULT", "fault:list", 0.8

    if utype == "clause":
        # 过程标准（ASPICE SYS/SWE/SUP/MAN/ACQ）→ 过程维度；产品标准条款 → R-STD
        if re.search(r"\b(SYS|SWE|SUP|MAN|ACQ)\.\d", text):
            return "G-PROC-STD", "clause:process-standard", 0.9
        if any(k in text for k in ("过程", "流程", "能力等级", "SPICE")):
            return "G-PROC-STD", "clause:process-keyword", 0.7
        return "R-STD", "clause", 0.8

    if utype == "experience":
        return None, "experience:needs-node", 0.3  # 骨架缺经验节点 → 增枝

    if utype == "process":
        for kw, nid in PROCESS_RULES:
            if kw in text:
                return nid, f"process:{kw}", 0.7
        return "G-ROOT", "process:default", 0.4

    if utype == "table_row":
        # SWRD 需求表格（含 SW4- 编号）→ 软件需求
        if re.search(r"\bSW4-\d+", text):
            return "R-SW", "table:swrd-req", 0.85, None
        # 信号定义表格（信号名称/上报逻辑/触发条件）→ 接口与通信
        if any(k in text for k in ("信号名称", "上报逻辑", "触发条件", "执行动作", "信号描述")):
            return "R-IF", "table:signal-def", 0.7, None
        # 保护信号（停机/过压/过流/Err）→ 保护电路（决策2：保护优先）
        if any(k in text for k in ("停机", "保护", "过压", "过流", "Err", "OCP", "OVP")):
            return "P-HW-CTRL-PROTECT", "table:protect", 0.7, None
        # 采样信号（决策1：硬件采样电路为主，软件 ADCSignal/监测组件为关联）
        if any(k in text for k in ("采样", "AD", "uC_", "滤波")):
            return "P-HW-CTRL-SENSE", "table:sense", 0.65, "P-SW-ASW-ADC"
        return "P-HW", "table:hw", 0.4, None

    if utype == "heading":
        # 需求分组标题（ID | 标题 | 分组名）→ 项目实例层的需求目录（M 分支）
        if re.match(r"^(MI-MD|R-|SWRD|SW4-)", text):
            return "M-MI", "heading:req-group", 0.5
        # 策略/组件文档标题 → 对应节点
        if "策略" in text:
            for kw, nid in STRATEGY_RULES:
                if kw in text:
                    return nid, f"heading:{kw}", 0.9
        if any(k in text for k in ("详细设计", "组件", "模块")):
            for kw, nid in COMPONENT_RULES:
                if re.search(kw, text, re.IGNORECASE):
                    return nid, f"heading:{kw}", 0.9
        return None, "heading:no-rule", 0.0

    if utype == "para":
        # 工具表格化段落（工具名/作用/配置）→ G-METHOD-TOOL
        if any(k in text for k in ("POLARION", "DaVinci", "Simulink", "Embedded Coder", "需求追溯",
                                   "变更管理", "代码生成", "AUTOSAR配置", "工具")):
            return "G-METHOD-TOOL", "para:tool-table", 0.6, None
        # 最佳实践/经验描述 → Q-LESSON
        if any(k in text for k in ("最佳实践", "常见问题", "解决方案", "项目经验")):
            return "Q-LESSON", "para:best-practice", 0.7, None
        # 决策C：知识/原理类 → 产品知识节点（挂产品节点下）
        if any(k in text for k in ("简介", "工作原理", "拓扑", "原理介绍", "基本结构")):
            if "dcdc" in low or "DCDC" in text:
                return "P-KNOW-DCDC", "para:know-dcdc", 0.7, None
            return "P-KNOW-OBC", "para:know-obc", 0.7, None
        # 控制逻辑细节（驱动/环路/占空比/PWM）→ L 层
        if re.search(r"(控制方式|关断点|占空比|PRD|CMPB|CMPSS|EPWM|环路|电流环|电压环|斜坡|duty|死区|频率更新|软开关|时序|驱动)", text, re.IGNORECASE):
            return "L-ROOT", "para:control-logic", 0.6, None
        # 功能/端口/边界描述 → F 层（软件功能描述）
        if any(k in text for k in ("功能", "端口", "边界", "接口")):
            return "F-ROOT", "para:function", 0.5, None
        # 决策3：测试/验证要求 → 验证过程（G 维度）
        if any(k in text for k in ("测试", "验证", "复测", "试验")):
            return "G-DEV", "para:verification", 0.5, None
        return None, "para:no-rule", 0.0, None

    return None, "para:no-rule", 0.0, None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc", default=None, help="单文档落位：指定文件名（从 manifest 查找）")
    parser.add_argument("--category", default=None, help="按 Athena 分类处理")
    parser.add_argument("--limit", type=int, default=0, help="限制文档数（0=全部）")
    parser.add_argument("--summary", action="store_true", help="批量模式只打印统计")
    parser.add_argument("--no-sync-xlsx", action="store_true", help="跳过自动同步骨架 Excel")
    args = parser.parse_args()

    from extract_units import extract_md, extract_docx, extract_xlsx, extract_pdf

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = [d for d in manifest["docs"] if d["ext"] in {".md", ".docx", ".xlsx", ".pdf"}]
    if args.doc:
        docs = [d for d in docs if d["name"] == args.doc]
        if not docs:
            raise SystemExit(f"manifest 中找不到文档: {args.doc}")
    if args.category:
        docs = [d for d in docs if d.get("category") == args.category]
    if args.limit:
        docs = docs[: args.limit]

    nodes = load_skeleton()

    # PDF 与同名 md 重复检测（md 优先，PDF 跳过）
    md_names = {d["name"][:-3] for d in docs if d["name"].endswith(".md")}
    # docx 与同名 md 重复检测（通道 1：去重）
    docx_dup = {d["name"][:-5] for d in docs if d["name"].endswith(".docx")} & md_names

    for d in docs:
        p = Path(d["path"])
        if p.suffix == ".pdf" and d["name"][:-4] in md_names:
            print(f"⏭️ {d['name']}: 与 md 版重复，跳过（md 版已落位）")
            continue
        if p.suffix == ".docx" and d["name"][:-5] in docx_dup:
            print(f"⏭️ {d['name']}: 与 md 版重复，跳过")
            continue
        if p.suffix == ".md":
            units = extract_md(p)
        elif p.suffix == ".docx":
            units = extract_docx(p)
        elif p.suffix == ".xlsx":
            units = extract_xlsx(p)
        elif p.suffix == ".pdf":
            units = extract_pdf(p)
        else:
            units = []
        records = []
        noise_units: list[dict] = []
        for u in units:
            if u.get("unit_type") == "noise":
                noise_units.append({"doc": u.get("doc", ""), "unit_id": u.get("unit_id", ""),
                                    "text": u.get("text", "")[:200],
                                    "line_no": u.get("line_no"), "reviewed": False})
                continue
            res = rule_match(u, nodes)
            node_id, rule, conf = res[0], res[1], res[2]
            related = res[3] if len(res) > 3 else None
            if node_id and node_id not in nodes:
                node_id = None
            records.append({
                "unit_id": u.get("unit_id", ""),
                "unit_type": u.get("unit_type", ""),
                "text": u.get("text", "")[:120],
                "node_id": node_id,
                "node_name": nodes[node_id]["name"] if node_id and node_id in nodes else None,
                "related_node": related,
                "confidence": conf,
                "rule": rule,
            })
        assigned = sum(1 for r in records if r["node_id"])
        # 通道 3：未归属非噪声单元 → 复核队列（可追踪不丢失）
        review_units = [r for r in records if not r["node_id"] and r["unit_type"] not in ("noise", "meta")]
        if review_units:
            review_file = ROOT / "docs" / "ontology" / "tree_skeleton" / "review_queue.json"
            existing = []
            if review_file.exists():
                existing = json.loads(review_file.read_text(encoding="utf-8"))
            for r in review_units:
                existing.append({"doc": d["name"], "unit_id": r["unit_id"],
                                 "unit_type": r["unit_type"], "text": r["text"][:200],
                                 "rule": r["rule"], "reviewed": False})
            review_file.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.summary:
            print(f"{d['name'][:42]:44s} | {len(records):5d} 单元 | 归属 {assigned:5d} ({assigned/max(len(records),1)*100:4.0f}%) | 噪声 {len(noise_units)} | 复核 {len(review_units)}")
            continue
        print(f"\n{'='*70}\n📄 {d['name']}（{d.get('category','')}）")
        print(f"内容单元 {len(records)}：归属 {assigned} | 未归属 {len(records)-assigned} | 噪声 {len(noise_units)}")
        if noise_units:
            # 决策4：噪声收集到单独文件（人工复核后再落）
            noise_file = ROOT / "docs" / "ontology" / "tree_skeleton" / "noise_collected.json"
            existing = []
            if noise_file.exists():
                existing = json.loads(noise_file.read_text(encoding="utf-8"))
            existing.extend(noise_units)
            noise_file.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  ⚠️ 噪声 {len(noise_units)} 条已收集到 noise_collected.json（待人工复核）")
        print(f"{'-'*70}")
        for r in records:
            mark = "✅" if r["node_id"] else "❓"
            node = f"{r['node_id']} {r['node_name']}" if r["node_id"] else "未归属"
            print(f"{mark} [{r['unit_type']}] {r['text'][:60]}")
            if r["node_id"]:
                print(f"    → {node}（{r['rule']}）")



if __name__ == "__main__":
    main()
    # 自动同步骨架 Excel（除非 --no-sync-xlsx）
    if "--no-sync-xlsx" not in sys.argv:
        try:
            import subprocess
            subprocess.run([sys.executable, str(ROOT / "agent_kb_core" / "validation" / "export_skeleton_xlsx.py"),
                            "--no-sync-xlsx"], capture_output=True, text=True, timeout=30)
        except Exception:
            pass  # 同步失败不阻塞落位
