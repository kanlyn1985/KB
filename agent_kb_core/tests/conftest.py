# -*- coding: utf-8 -*-
"""agent_kb_core tests root conftest。

Production DB Isolation session hooks + fixtures 见 conftest_prod_isolation.py
（经 pytest_plugins 显式注册——非 conftest 命名文件需显式引入）。
"""
from __future__ import annotations

from pathlib import Path

pytest_plugins = ["conftest_prod_isolation"]
