from __future__ import annotations


SYNONYM_MAP: dict[str, list[str]] = {
    "充电导引": [
        "控制导引",
        "控制导引电路",
        "充电控制导引电路",
    ],
    "导引电路": [
        "控制导引电路",
        "充电控制导引电路",
    ],
    "导引功能": [
        "控制导引功能",
        "control pilot function",
    ],
    "车网互动": [
        "V2G",
        "Vehicle-to-Grid",
        "电动汽车与电网充放电双向互动",
    ],
    "车网": [
        "V2G",
        "Vehicle-to-Grid",
    ],
    "车载充电机": [
        "电动汽车用传导式车载充电机",
        "on-board charger",
        "OBC",
    ],
    "OBC": [
        "车载充电机",
        "电动汽车用传导式车载充电机",
        "on-board charger",
        "onboard charger",
    ],
    "CC": [
        "CC1",
        "CC2",
        "控制导引",
        "控制导引电路",
    ],
    "CP": [
        "控制导引",
        "控制导引电路",
        "control pilot",
        "检测点",
    ],
}


def expand_with_synonyms(query: str) -> list[str]:
    expansions: list[str] = []
    for key, values in SYNONYM_MAP.items():
        if key in query:
            expansions.extend(values)
    return expansions
