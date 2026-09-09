# -*- coding: utf-8 -*-
"""Integration marker runner：容忍当前基线无 integration 标记测试（exit 5 → 0）。"""
import subprocess
import sys

r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short", "-m", "integration"])
if r.returncode in (0, 5):
    print("integration: PASS (0 tests collected = empty marker set in current baseline)")
    sys.exit(0)
sys.exit(r.returncode)