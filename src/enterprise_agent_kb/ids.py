from __future__ import annotations

import sqlite3


def next_prefixed_id(
    connection: sqlite3.Connection,
    counter_key: str,
    prefix: str,
    width: int = 6,
) -> str:
    current = connection.execute(
        "SELECT next_value FROM system_counters WHERE counter_key = ?",
        (counter_key,),
    ).fetchone()

    if current is None:
        value = 1
        connection.execute(
            "INSERT INTO system_counters(counter_key, next_value) VALUES(?, ?)",
            (counter_key, value + 1),
        )
    else:
        value = int(current["next_value"])
        connection.execute(
            "UPDATE system_counters SET next_value = ? WHERE counter_key = ?",
            (value + 1, counter_key),
        )

    return f"{prefix}-{value:0{width}d}"

