# -*- coding: utf-8 -*-
"""agent_kb_core tests root conftest。

Production DB Isolation session hooks + fixtures 定义在 conftest_prod_isolation.py，
在此显式导入以注册（pytest_plugins 限顶层 conftest，故用 import 绑定）。
"""
from __future__ import annotations

from pathlib import Path

if (Path(__file__).resolve().parent / "conftest_prod_isolation.py").exists():
    from conftest_prod_isolation import (  # noqa: F401
        prod_db_path,
        prod_isolation_evidence,
        pytest_sessionfinish,
        pytest_sessionstart,
    )
