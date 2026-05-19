from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .config import AppPaths
from .db import apply_schema, connect, list_tables


def initialize_workspace(root: Path, schema_path: Path) -> AppPaths:
    paths = AppPaths.from_root(root)
    for directory in paths.all_dirs():
        directory.mkdir(parents=True, exist_ok=True)

    connection = connect(paths.db_file)
    try:
        apply_schema(connection, schema_path)
    finally:
        connection.close()

    return paths


def workspace_status(root: Path) -> dict[str, object]:
    paths = AppPaths.from_root(root)
    exists = paths.root.exists()
    db_exists = paths.db_file.exists()

    tables: list[str] = []
    if db_exists:
        connection = connect(paths.db_file)
        try:
            tables = list_tables(connection)
        finally:
            connection.close()

    return {
        "workspace_exists": exists,
        "db_exists": db_exists,
        "paths": {key: str(value) for key, value in asdict(paths).items()},
        "tables": tables,
    }

