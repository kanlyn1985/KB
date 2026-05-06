from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .ambiguity_index import Sense, load_ambiguity_index


@dataclass(frozen=True)
class ClarificationOption:
    option_id: str
    label: str
    description: str
    example_query: str
    context_terms: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class QueryAmbiguity:
    ambiguous: bool
    ambiguity_type: str
    anchor: str
    question: str
    options: list[ClarificationOption]
    reason: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["options"] = [asdict(item) for item in self.options]
        return payload


AMBIGUOUS_ACRONYMS: dict[str, list[ClarificationOption]] = {
    "CC": [
        ClarificationOption(
            option_id="connection_confirm",
            label="连接确认功能 / connection confirm",
            description="电动汽车充电接口语境，表示通过电子或机械方式反映插头连接状态的功能。",
            example_query="充电接口里的 CC 连接确认功能是什么意思",
            context_terms=(
                "连接确认",
                "车辆插头",
                "车辆插座",
                "供电接口",
                "充电接口",
                "控制导引",
                "检测点",
                "GB/T 18487",
                "GBT 18487",
                "GB/T 20234",
                "GBT 20234",
                "CC1",
                "CC2",
                "阻值",
                "电阻",
            ),
        ),
        ClarificationOption(
            option_id="constant_current",
            label="恒流 / constant current",
            description="电源、充电策略或电池充电语境，表示电流保持恒定的工作模式。",
            example_query="充电策略里的 CC 恒流是什么意思",
            context_terms=("恒流", "CONSTANT CURRENT", "充电策略", "电池", "电源模式", "CV", "恒压"),
        ),
        ClarificationOption(
            option_id="other_context",
            label="其他语境",
            description="如果来自其他标准、行业或章节，需要补充文档名、标准号或上下文。",
            example_query="某某标准里的 CC 是什么意思",
            context_terms=("其他语境", "标准", "章节"),
        ),
    ],
    "CP": [
        ClarificationOption(
            option_id="control_pilot_function",
            label="控制导引功能 / control pilot",
            description="电动汽车交流充电语境，表示用于监控电动汽车和供电设备之间交互的控制导引功能。",
            example_query="充电接口里的 CP 控制导引功能是什么意思",
            context_terms=(
                "控制导引",
                "充电接口",
                "车辆接口",
                "供电设备",
                "电动汽车",
                "GB/T 18487",
                "GBT 18487",
                "GB/T 20234",
                "GBT 20234",
            ),
        ),
        ClarificationOption(
            option_id="control_pilot_circuit_or_signal",
            label="控制导引电路或信号",
            description="控制导引电路、检测点电压、PWM、占空比或时序等参数语境。",
            example_query="控制导引电路里的 CP 信号是什么意思",
            context_terms=("控制导引电路", "检测点", "PWM", "占空比", "电压", "时序", "信号"),
        ),
        ClarificationOption(
            option_id="other_context",
            label="其他语境",
            description="如果来自电子、电源、芯片或其他标准语境，需要补充文档名、标准号或上下文。",
            example_query="某某标准里的 CP 是什么意思",
            context_terms=("CHARGE PUMP", "CONTROL PIN", "CLOCK PULSE", "芯片", "电源", "泵", "其他语境"),
        ),
    ],
    "PE": [
        ClarificationOption(
            option_id="protective_earth",
            label="保护接地 / protective earth",
            description="充电接口、电气安全或接地语境，表示保护接地导体或端子。",
            example_query="充电接口里的 PE 保护接地是什么意思",
            context_terms=("保护接地", "接地", "充电接口", "车辆接口", "PE端子", "GB/T 18487", "GB/T 20234"),
        ),
        ClarificationOption(
            option_id="other_context",
            label="其他语境",
            description="如果来自材料、工程、软件或其他标准语境，需要补充上下文。",
            example_query="某某标准里的 PE 是什么意思",
            context_terms=("其他语境", "标准", "章节"),
        ),
    ],
    "OBC": [
        ClarificationOption(
            option_id="on_board_charger",
            label="车载充电机 / on-board charger",
            description="电动汽车充电系统语境，表示安装在车辆上的充电机。",
            example_query="电动汽车里的 OBC 车载充电机是什么意思",
            context_terms=("车载充电机", "电动汽车", "充电系统", "交流充电", "车辆"),
        ),
        ClarificationOption(
            option_id="other_context",
            label="其他语境",
            description="如果来自其他行业或标准，需要补充文档名、标准号或上下文。",
            example_query="某某标准里的 OBC 是什么意思",
            context_terms=("其他语境", "标准", "章节"),
        ),
    ],
    "V2G": [
        ClarificationOption(
            option_id="vehicle_to_grid",
            label="车网互动 / vehicle-to-grid",
            description="车辆与电网能量交互语境。",
            example_query="V2G 车网互动是什么意思",
            context_terms=("车网互动", "电网", "能量回馈", "双向充电", "vehicle-to-grid"),
        ),
        ClarificationOption(
            option_id="other_context",
            label="其他语境",
            description="如果不是车网互动语境，需要补充上下文。",
            example_query="某某标准里的 V2G 是什么意思",
            context_terms=("其他语境", "标准", "章节"),
        ),
    ],
    "V2X": [
        ClarificationOption(
            option_id="vehicle_to_everything",
            label="车联万物 / vehicle-to-everything",
            description="车辆与外部对象通信或能量交互语境。",
            example_query="V2X 是什么意思",
            context_terms=("车联万物", "通信", "能量交互", "vehicle-to-everything", "车辆"),
        ),
        ClarificationOption(
            option_id="other_context",
            label="其他语境",
            description="如果来自其他标准或行业，需要补充上下文。",
            example_query="某某标准里的 V2X 是什么意思",
            context_terms=("其他语境", "标准", "章节"),
        ),
    ],
}


def detect_query_ambiguity(query: str) -> QueryAmbiguity | None:
    stripped = query.strip()
    if not stripped:
        return None
    acronym = _short_definition_acronym(stripped)
    if not acronym or acronym not in AMBIGUOUS_ACRONYMS:
        return None
    if _has_disambiguating_context(stripped, acronym):
        return None
    return QueryAmbiguity(
        ambiguous=True,
        ambiguity_type="short_acronym_definition",
        anchor=acronym,
        question=f"{acronym} 有多个可能含义，请先确认你问的是哪一种？",
        options=AMBIGUOUS_ACRONYMS[acronym],
        reason="short acronym definition query lacks enough domain context",
    )


def _short_definition_acronym(query: str) -> str:
    if not re.search(r"(是什么意思|是什么|定义|含义|代表什么|表示什么|指什么)", query):
        return ""
    matches = re.findall(r"(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9])", query, re.I)
    if len(matches) != 1:
        return ""
    return matches[0].upper()


def _has_disambiguating_context(query: str, acronym: str) -> bool:
    text = query.upper()
    options = AMBIGUOUS_ACRONYMS.get(acronym, [])
    return any(
        term and term.upper() in text
        for option in options
        for term in option.context_terms
    )


_kb_index_cache: dict[str, list[Sense]] | None = None
_kb_index_path: str | None = None


def _load_kb_index() -> dict[str, list[Sense]]:
    global _kb_index_cache, _kb_index_path
    default_path = str(Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "ambiguity_index.json")
    path = _kb_index_path or default_path
    if _kb_index_cache is None or _kb_index_path != path:
        _kb_index_cache = load_ambiguity_index(path)
        _kb_index_path = path
    return _kb_index_cache


def reload_kb_index(path: str | None = None) -> None:
    global _kb_index_cache, _kb_index_path
    if path:
        _kb_index_path = path
    _kb_index_cache = None


def detect_query_ambiguity_with_kb(query: str) -> QueryAmbiguity | None:
    stripped = query.strip()
    if not stripped:
        return None
    acronym = _short_definition_acronym(stripped)
    if not acronym:
        return None

    kb_index = _load_kb_index()
    kb_senses = kb_index.get(acronym)

    if kb_senses and len(kb_senses) >= 2:
        if _has_kb_disambiguating_context(stripped, kb_senses):
            return None
        options = [
            ClarificationOption(
                option_id=sense.entity_id or sense.label[:20],
                label=sense.label,
                description=f"来源：知识库 ({sense.label})",
                example_query=sense.example_query,
                context_terms=tuple(sense.context_terms[:8]),
            )
            for sense in kb_senses
        ]
        return QueryAmbiguity(
            ambiguous=True,
            ambiguity_type="short_acronym_definition",
            anchor=acronym,
            question=f"{acronym} 有多个可能含义，请先确认你问的是哪一种？",
            options=options,
            reason="KB-driven ambiguity detection: acronym has multiple senses",
        )

    return detect_query_ambiguity(query)


def _has_kb_disambiguating_context(query: str, senses: list[Sense]) -> bool:
    text = query.upper()
    return any(
        term and term.upper() in text
        for sense in senses
        for term in sense.context_terms
    )
