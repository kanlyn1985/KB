#!/usr/bin/env python3
"""LLM 语义分解：查询 → 骨架节点映射（方案 D）。

规则匹配不确定时（无目标对象 / 多目标冲突 / 泛词匹配），调用 LLM
把查询映射到骨架节点，作为 target_objects 的增强。

触发条件（在 understand_query 中判定）：
  1. 无目标对象
  2. 目标对象 ≥2 且含短别名（≤3 字符）匹配
  3. 最佳匹配词 ≤3 字符（泛词）

输出：TargetObject 列表（object_id / confidence / reason），
LLM 返回 JSON，代码白名单校验（只接受术语表存在的节点）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # agent_kb_core/
sys.path.insert(0, str(ROOT / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.query.query_frame import TargetObject  # noqa: E402

# LLM 调用（复用 validation/llm_client.py，网关 EVT/deepseek-v4-flash）
_LLM_AVAILABLE = False
try:
    import importlib.util
    _client_path = ROOT.parent / "validation" / "llm_client.py"
    if _client_path.exists():
        _spec = importlib.util.spec_from_file_location("kb_llm_client", _client_path)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        chat = _mod.chat
        extract_json = _mod.extract_json
        _LLM_AVAILABLE = True
except Exception:  # noqa: BLE001
    chat = None  # type: ignore[assignment]
    extract_json = None  # type: ignore[assignment]

SYSTEM_PROMPT = """你是知识库查询语义分解器。用户查询会被映射到知识骨架的节点。

节点目录格式：`ID | 层级 | 类型 | 名称`
层级含义：
- P 物理分解（电子/结构/磁件/软件；零件、电路、SW-C 组件）
- F 功能分解（充放电、对外服务等功能）
- L 逻辑/策略（控制策略、算法、保护逻辑）
- R 需求与标准（性能/安全/接口/法规标准）
- G 过程（开发/生产/方法/验证测试/资产工具）
- Q 质量与经验（问题、失效、经验教训）
- M 项目实例（车型/项目/平台实例）

任务：把查询映射到**最贴切的 1-3 个节点**。
规则：
1. object_id 只能从目录选，禁止编造。
2. 查询含多个主题时，按重要度排序返回多个。
3. 无法映射到任何节点 → 返回空列表，reason 说明。
4. conf 是把握度 0~1；把握不足（conf < 0.6）时不要返回。

只输出一个 JSON 对象：
{"targets": [{"object_id": "P-...", "conf": 0.9, "reason": "简短理由"}]}"""


def _build_catalog(domain_pack) -> str:
    lines = []
    for nid, term in domain_pack.terminology.items():
        aliases = term if isinstance(term, list) else term.get("aliases", [])
        lines.append(f"{nid} | {' / '.join(aliases[:4])}")
    return "\n".join(lines)


def llm_link_targets(query: str, domain_pack) -> list[TargetObject]:
    """LLM 把查询映射到骨架节点，返回 TargetObject 列表。

    LLM 不可用（网关故障/超时/解析失败）时返回 []，调用方回退到规则结果。
    """
    if not _LLM_AVAILABLE or chat is None or extract_json is None:
        return []
    catalog = _build_catalog(domain_pack)
    user = f"查询: {query}\n\n节点目录:\n{catalog}"
    try:
        raw = chat(user, system=SYSTEM_PROMPT, max_tokens=1024, timeout=60, retries=2)
    except Exception:  # noqa: BLE001  网关故障 → 回退规则
        return []
    if not raw or not raw.strip():
        return []
    parsed = extract_json(raw)
    if not isinstance(parsed, dict) or "targets" not in parsed:
        return []
    result: list[TargetObject] = []
    for t in parsed["targets"]:
        if not isinstance(t, dict):
            continue
        nid = str(t.get("object_id") or "")
        if nid not in domain_pack.terminology:
            continue  # 白名单校验
        conf = float(t.get("conf") or 0.0)
        if conf < 0.6:
            continue
        aliases = domain_pack.terminology[nid] if isinstance(domain_pack.terminology[nid], list) else domain_pack.terminology[nid].get("aliases", [])
        result.append(TargetObject(
            object_id=nid,
            object_type=_infer_type(nid),
            canonical_name=aliases[0] if aliases else nid,
            matched_text=query,
            confidence=conf,
        ))
    return result[:3]


def _infer_type(nid: str) -> str:
    prefix = nid.split("-", 1)[0] if "-" in nid else nid
    mapping = {"P": "PhysicalComponent", "F": "Function", "L": "Logic",
               "R": "Requirement", "G": "Process", "Q": "Experience",
               "M": "ProjectInstance"}
    return mapping.get(prefix, "Concept")


def rule_match_is_uncertain(query: str, targets: list[TargetObject]) -> bool:
    """判断规则匹配是否不确定（需 LLM 增强）。"""
    if not targets:
        return True
    if len(targets) >= 2:
        # 含短别名匹配（≤3 字符）→ 冲突
        for t in targets:
            if len(t.matched_text) <= 3:
                return True
    if len(targets) == 1 and len(targets[0].matched_text) <= 3:
        return True
    return False
