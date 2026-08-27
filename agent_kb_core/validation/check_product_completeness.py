#!/usr/bin/env python3
"""产品完备性检查器 v0.4 —— 独立标准（三条公理）

把「骨架」当作被测对象，用三条**独立于骨架**的公理逐条核对：

  公理1 覆盖 Coverage     —— 完整产品必须覆盖一套固定「必备要素清单」
                            （清单来自领域知识+标准+系统工程V模型，不来自骨架）
  公理2 深度 Depth        —— 每个节点必须有足够落地内容（能执行，不只是名字）
                            （按节点逐个统计：无卡/薄/充分，不做概念映射）
  公理3 连接 Connectivity —— 要素之间必须连成链（需求->功能->逻辑->物理->工艺/验证）
                            （可追溯性来自V模型，不来自骨架的关系格式）

用法: python check_product_completeness.py [--json]
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.4.json"
CARDS = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "node_cards.jsonl"

# ============ 公理1：独立「必备要素清单」 ============
CHECKLIST = [
    ("REQ", "需求层：先定义「要满足什么」", "V模型/GB/T 40432/ISO 26262", [
        ("REQ-PERF", "性能需求（效率/纹波/功率因数/THD）", ["效率", "纹波", "功率因数", "THD"]),
        ("REQ-FUSA", "功能安全（安全目标/ASIL/FSR/TSR）", ["功能安全", "ISO 26262", "ASIL", "安全目标"]),
        ("REQ-ELEC", "电气安全（绝缘/耐压/爬电/接触电流）", ["绝缘", "耐压", "爬电", "接触电流"]),
        ("REQ-EMC", "电磁兼容（传导/辐射发射/抗扰度）", ["EMC", "电磁兼容", "传导", "辐射", "抗扰"]),
        ("REQ-ENV", "环境适应性（温度/湿度/盐雾/IP/振动）", ["环境", "温度", "湿度", "盐雾", "防护等级"]),
        ("REQ-REL", "可靠性（寿命/MTBF/耐久）", ["可靠性", "寿命", "MTBF", "耐久"]),
        ("REQ-IF", "接口与通信（CAN矩阵/连接定义）", ["接口", "CAN 矩阵", "通信矩阵"]),
        ("REQ-STD", "标准符合性（GB/T 40432/18487/14229/15118）", ["GB/T", "40432", "18487", "14229", "15118"]),
    ]),
    ("FUNC", "功能层：定义「能做什么」", "领域知识/黑盒功能分解", [
        ("FUNC-CHARGE", "充电功能（AC-DC变换/电压调节/电流限制）", ["充电", "AC-DC", "电压调节", "电流限制"]),
        ("FUNC-DCDC", "DC-DC转换（低压输出）", ["DCDC", "电压转换", "低压输出"]),
        ("FUNC-DISCHARGE", "放电功能（V2L/V2G/V2H逆变）", ["放电", "V2L", "V2G", "V2H", "逆变"]),
        ("FUNC-CP", "控制导引（CP/CC/锁止）", ["控制导引", "CP", "锁止"]),
        ("FUNC-PROTECT", "保护功能（过压/欠压/过流/短路/过温/绝缘监测）", ["保护", "过压", "欠压", "过流", "短路", "过温"]),
        ("FUNC-COMM", "通信功能（CAN/UDS/15118）", ["通信", "CAN", "UDS", "15118"]),
        ("FUNC-DIAG", "诊断功能（DTC/故障记录）", ["诊断", "DTC"]),
        ("FUNC-WAKE", "待机唤醒（休眠/唤醒/继电器控制）", ["唤醒", "休眠", "待机"]),
    ]),
    ("LOGIC", "逻辑/软件层：定义「怎么实现」", "AUTOSAR分层/领域知识", [
        ("LOGIC-PWRCTRL", "功率控制逻辑（环路/调制/PWM）", ["功率控制", "环路", "调制", "PWM"]),
        ("LOGIC-STATE", "状态管理（充电/休眠状态机）", ["状态机", "状态管理"]),
        ("LOGIC-FAULT", "故障判定（检测/判定/恢复）", ["故障", "判定", "检测"]),
        ("LOGIC-COMM", "通信协议（CAN/UDS/网络管理）", ["通信协议", "网络管理"]),
        ("LOGIC-CAL", "标定逻辑（参数/降额）", ["标定", "降额"]),
        ("LOGIC-SENSE", "采样监测（电压/电流/温度）", ["采样", "监测"]),
        ("LOGIC-STRATEGY", "控制策略（抖频/CBC/峰值/预充/NTC/低温/V2L）", ["策略", "抖频", "CBC", "预充", "峰值"]),
        ("LOGIC-MCAL", "底层驱动MCAL（ADC/SPI/GPIO/PWM/WDG）", ["MCAL", "ADC", "SPI", "GPIO", "WDG"]),
        ("LOGIC-BSW", "基础软件BSW（通信栈/诊断/NVM）", ["BSW", "通信栈", "NVM"]),
        ("LOGIC-RTE", "运行时环境RTE", ["RTE"]),
    ]),
    ("HW", "物理硬件层：定义「由什么组成」", "爆炸图分解/领域知识", [
        ("HW-EMI", "EMI滤波电路", ["EMI", "滤波"]),
        ("HW-PFC", "PFC电路", ["PFC"]),
        ("HW-LLC", "隔离变换级（LLC/谐振）", ["LLC", "隔离", "变换"]),
        ("HW-OUTPUT", "输出电路（整流/滤波）", ["输出", "整流"]),
        ("HW-AUX", "辅助电源", ["辅助电源"]),
        ("HW-MCU", "主控（MCU/DSP）", ["MCU", "DSP"]),
        ("HW-DRIVER", "驱动电路", ["驱动"]),
        ("HW-SENSE", "采样电路", ["采样"]),
        ("HW-PROTECT", "保护电路", ["保护电路"]),
        ("HW-MAG", "磁性元件（变压器/电感）", ["变压器", "电感", "磁性"]),
        ("HW-RELAY", "继电器", ["继电器"]),
        ("HW-HOUSING", "壳体", ["壳体"]),
        ("HW-WATERWAY", "水道/水冷", ["水道", "水冷", "流道"]),
        ("HW-SEAL", "密封系统（O型圈/密封垫/密封胶）", ["密封", "O型圈", "密封垫"]),
        ("HW-FASTENER", "紧固件（螺钉/螺栓/螺母）", ["紧固件", "螺钉", "螺栓"]),
        ("HW-CONNECTOR", "连接器/接插件", ["连接器", "接插件"]),
        ("HW-BUSBAR", "铜排/母排", ["铜排", "母排"]),
        ("HW-NAMEPLATE", "铭牌/标签/标识", ["铭牌", "标签"]),
        ("HW-SHIELD", "屏蔽与防护", ["屏蔽", "防护"]),
        ("HW-BRACKET", "支架/托架/安装结构", ["支架", "托架"]),
        ("HW-HARNESS", "线束", ["线束"]),
        ("HW-HEATSINK", "散热器", ["散热器", "散热"]),
        ("HW-TIM", "导热界面材料（导热垫/硅脂）", ["导热", "TIM", "硅脂"]),
        ("HW-FAN", "风冷部件（风扇/风道）", ["风冷", "风扇", "风道"]),
        ("HW-POTTING", "灌封涂覆（灌封胶/三防漆）", ["灌封", "涂覆", "三防"]),
        ("HW-METAL", "金属材料（铝/铜/钢/磁材）", ["金属", "铝", "铜", "ADC12"]),
        ("HW-PLASTIC", "工程塑料（PA/PPA/PBT/PC）", ["塑料", "PBT", "PC"]),
        ("HW-RUBBER", "橡胶/硅胶/弹性体", ["橡胶", "硅胶", "弹性体"]),
        ("HW-SURFACE", "表面处理（阳极氧化/电镀/喷涂）", ["表面处理", "阳极", "电镀"]),
    ]),
    ("MFG", "制造工艺层：定义「怎么做出来」", "制造工程/IPC", [
        ("MFG-CASTING", "压铸工艺", ["压铸"]),
        ("MFG-MACHINING", "机加工（CNC/钻孔/攻丝）", ["机加工", "CNC", "攻丝"]),
        ("MFG-SHEET", "钣金（冲压/折弯）", ["钣金", "冲压", "折弯"]),
        ("MFG-INJECTION", "注塑工艺", ["注塑"]),
        ("MFG-SURFACE", "表面处理工艺（阳极/电镀/喷涂/钝化）", ["喷涂", "钝化"]),
        ("MFG-POTTING", "灌封涂覆工艺（灌胶/点胶）", ["灌胶", "点胶"]),
        ("MFG-ASSEMBLY", "装配工艺", ["装配", "组装"]),
        ("MFG-PACK", "包装工艺", ["包装"]),
        ("MFG-FASTEN", "螺纹紧固（扭矩/预紧）", ["螺纹紧固", "扭矩", "预紧"]),
        ("MFG-PRESS", "压装压接", ["压装", "压接"]),
        ("MFG-BOND", "涂胶密封", ["涂胶", "点胶密封"]),
        ("MFG-FIXTURE", "工装治具", ["工装", "治具", "夹具"]),
    ]),
    ("VERIFY", "验证测试层：定义「怎么证明做对了」", "V模型验证", [
        ("VERIFY-THERMAL", "热测试（温升/热循环）", ["热测试", "温升", "热循环"]),
        ("VERIFY-VIBRATION", "振动冲击测试（振动/跌落）", ["振动", "冲击", "跌落"]),
        ("VERIFY-AIRTIGHT", "气密泄漏测试（气密/氦检）", ["气密", "泄漏", "氦检"]),
        ("VERIFY-ENV", "环境测试（高温/低温/湿热/盐雾）", ["环境测试", "高温", "低温", "湿热"]),
        ("VERIFY-DIM", "尺寸检测（三坐标/CPK）", ["尺寸检测", "三坐标", "CPK"]),
        ("VERIFY-REL", "可靠性试验（耐久/老化）", ["可靠性试验", "耐久", "老化"]),
        ("VERIFY-ELECTRICAL", "电气测试（耐压/绝缘）", ["电气测试", "耐压", "绝缘"]),
        ("VERIFY-CAE", "CAE仿真验证（热/结构/流阻）", ["仿真验证", "CAE", "Flotherm"]),
    ]),
    ("METHOD", "方法层：定义「用什么方法设计」", "ASPICE/工程方法", [
        ("METHOD-MBD", "MBD建模（Simulink/Stateflow）", ["MBD", "Simulink", "Stateflow"]),
        ("METHOD-AUTOSAR", "AUTOSAR配置（ARXML/代码生成）", ["AUTOSAR", "ARXML"]),
        ("METHOD-CAE", "CAE仿真方法（热/结构/流场）", ["仿真方法", "热仿真", "结构仿真"]),
        ("METHOD-DFM", "DFM/DFA可制造性设计", ["DFM", "DFA", "可制造"]),
        ("METHOD-TOL", "公差分析（尺寸链/GD&T）", ["公差", "GD&T", "尺寸链"]),
    ]),
    ("QUALITY", "质量经验层：沉淀「踩过的坑」", "经验管理/FMEA", [
        ("QUALITY-PROBLEM", "问题记录（排查/踩坑）", ["问题", "排查", "踩坑"]),
        ("QUALITY-LESSON", "经验教训（复盘/FAQ）", ["经验", "教训", "复盘", "FAQ"]),
        ("QUALITY-FAILURE", "失效模式（FMEA）", ["失效", "FMEA"]),
    ]),
    ("INSTANCE", "实例层：落地到「具体产品」", "实例化/型号管理", [
        ("INSTANCE-MODEL", "产品型号（如CCU）", ["型号", "CCU"]),
        ("INSTANCE-PROJECT", "项目实例（曼岛/零跑/VAVE）", ["项目", "曼岛", "零跑", "VAVE"]),
        ("INSTANCE-PLATFORM", "平台实例（G5/G7）", ["平台", "G5", "G7"]),
    ]),
]

DOC_MIN = 5    # 深度阈值（独立判断：少于 5 篇文档不足以落地执行）
UNIT_MIN = 10

def load():
    sk = json.loads(SKELETON.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in sk["nodes"]}
    cards = {}
    for line in CARDS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if "#" not in c["node_id"]:
            cards[c["node_id"]] = c
    return sk, nodes, cards

def main():
    sk, nodes, cards = load()
    children = defaultdict(list)
    for nid, n in nodes.items():
        if n.get("parent"):
            children[n["parent"]].append(nid)

    # ---- 公理1 覆盖：独立清单逐条查「是否命名」 ----
    texts = {nid: ((n.get("name") or "") + " " + " ".join(cards.get(nid, {}).get("aliases") or [])).lower() for nid, n in nodes.items()}
    total_items = 0
    covered_items = 0
    uncovered_items = []
    dim_summary = []
    for dim_id, dim_name, dim_src, items in CHECKLIST:
        d_cov = 0
        for item_id, item_name, kws in items:
            total_items += 1
            hits = [nid for nid, t in texts.items() if any(k.lower() in t for k in kws)]
            if hits:
                covered_items += 1; d_cov += 1
            else:
                uncovered_items.append((dim_id, item_id, item_name))
        dim_summary.append((dim_id, dim_name, d_cov, len(items)))

    # ---- 公理2 深度：节点层面逐个统计 ----
    no_card, thin, rich = [], [], []
    for nid, n in nodes.items():
        c = cards.get(nid)
        if c is None:
            no_card.append(nid); continue
        doc = c.get("doc_count", 0); unit = c.get("unit_count", 0)
        if doc < DOC_MIN or unit < UNIT_MIN:
            thin.append((nid, doc, unit))
        else:
            rich.append(nid)

    # ---- 公理3 连接：V模型可追溯链 ----
    out_edges = defaultdict(list)
    for r in sk.get("relations", []):
        out_edges[r["source"]].append(r["target"])
    lay = lambda nid: nodes[nid]["layer"] if nid in nodes else "?"
    R = [nid for nid, n in nodes.items() if n["layer"] == "R" and n.get("parent") == "R-ROOT"]
    F = [nid for nid, n in nodes.items() if n["layer"] == "F" and n["type"] == "功能"]
    L = [nid for nid, n in nodes.items() if n["layer"] == "L" and n["type"] in ("组件", "策略")]
    P_leaves = [nid for nid, n in nodes.items() if n["layer"] == "P" and not children.get(nid) and n["type"] in ("电路","部件","器件","材料","SW-C 组件")]
    def has_edge(src, tlayer): return any(lay(t) == tlayer for t in out_edges.get(src, []))
    conn = [
        ("R->F 需求被功能满足", sum(1 for r in R if has_edge(r, "F")), len(R)),
        ("F->L 功能被逻辑实现", sum(1 for f in F if has_edge(f, "L")), len(F)),
        ("L->P 逻辑分配到物理", sum(1 for l in L if has_edge(l, "P")), len(L)),
        ("P->G 物理被工艺/验证覆盖", sum(1 for p in P_leaves if has_edge(p, "G")), len(P_leaves)),
    ]
    rel_total = len(sk.get("relations", []))
    rel_evid = sum(1 for r in sk.get("relations", []) if r.get("evidence_refs"))

    pct = lambda a, b: (100.0 * a / b) if b else 0.0
    if "--json" in sys.argv[1:]:
        print(json.dumps({
            "coverage": {"covered": covered_items, "total": total_items, "uncovered": uncovered_items},
            "depth": {"no_card": no_card, "thin": thin, "rich_count": len(rich), "node_total": len(nodes)},
            "connectivity": [{"chain": c[0], "done": c[1], "total": c[2]} for c in conn],
            "relations_evidence": [rel_evid, rel_total],
        }, ensure_ascii=False, indent=2))
        return

    print("=" * 72)
    print("产品完备性报告（独立标准 v0.4 · 三条公理）")
    print(f"被测: skeleton_v0.4.json ({len(nodes)} 节点)")
    print("=" * 72)

    print(f"\n[公理1 覆盖]  独立必备要素清单（来自领域+标准+V模型，不来自骨架）")
    print(f"  已命名 {covered_items}/{total_items} = {pct(covered_items,total_items):.1f}%")
    for dim_id, dim_name, c, t in dim_summary:
        print(f"    {dim_id:8s} {c:2d}/{t}")
    if uncovered_items:
        print(f"  未覆盖: {[(d+':'+i) for d,i,_ in uncovered_items]}")

    print(f"\n[公理2 深度]  每个节点必须有足够落地内容（按 {len(nodes)} 节点逐个统计）")
    print(f"  充分:  {len(rich)}/{len(nodes)} = {pct(len(rich),len(nodes)):.1f}%")
    print(f"  薄:    {len(thin)}/{len(nodes)}  (doc<{DOC_MIN} 或 unit<{UNIT_MIN})")
    print(f"  无卡:  {len(no_card)}/{len(nodes)}")
    if no_card: print(f"    无卡节点: {no_card}")
    if thin: print(f"    薄节点: {[(n, f'doc={d}', f'unit={u}') for n, d, u in thin]}")

    print(f"\n[公理3 连接]  V模型可追溯链（要素之间必须连成链，来自V模型不来自骨架）")
    for name, done, tot in conn:
        print(f"  {name:26s} {done:3d}/{tot:<3d} = {pct(done,tot):5.1f}%")
    print(f"  关联证据覆盖:                {rel_evid:3d}/{rel_total:<3d} = {pct(rel_evid,rel_total):5.0f}%")
    print()

if __name__ == "__main__":
    main()