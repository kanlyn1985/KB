"""LLM 调用层（zcode 主模型：韬-GLM5.2 / deepseek-v4-pro-0813）。

Anthropic Messages 兼容端点（http://ssh-yw.tianshanzhigu.cn:25156），
全局处理：重试/退避、思考块剥离、JSON 提取、token 计量。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> dict[str, str]:
    """读仓库根 .env；文件不存在（CI 沙箱/新 clone）时返回空 dict，
    让模块仍可导入（BASE_URL 用默认值，API_KEY 为空——真调用时才失败，
    mock 测试不受影响）。"""
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        return env
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except OSError:
        pass
    return env


ENV = load_env()
BASE_URL = ENV.get("ZCODE_BASE_URL", "http://ssh-yw.tianshanzhigu.cn:25156").rstrip("/")
API_KEY = ENV.get("ZCODE_API_KEY", "")
MODEL = ENV.get("ZCODE_MODEL", "deepseek-v4-pro-0813")

USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "errors": 0}


def chat(
    user: str,
    *,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float | None = None,
    timeout: int = 300,
    retries: int = 5,
    usage: dict | None = None,
    thinking: bool = False,
) -> str:
    """单轮对话，返回拼接后的文本内容（自动剥离 thinking 块）。

    thinking=True 时保留模型推理块（慢 9 倍，仅调试用）；
    默认关闭推理以提速。失败重试（指数退避），最终失败抛 RuntimeError。
    """
    usage = usage if usage is not None else USAGE
    body: dict = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user}],
    }
    if system:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = temperature
    if not thinking:
        body["thinking"] = {"type": "disabled"}
    if not usage.get("model"):
        usage["model"] = MODEL

    url = BASE_URL + "/v1/messages"
    last_err: Exception | None = None
    # 直连网关：内网 IP 不走系统代理（HTTP_PROXY/ALL_PROXY 会经本地代理
    # 转发，代理不稳定时导致调用失败——实测直连 200 正常）
    _direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY,
                "Authorization": f"Bearer {API_KEY}",
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with _direct_opener.open(req, timeout=timeout) as r:
                resp = json.loads(r.read())
            usage["calls"] += 1
            u = resp.get("usage") or {}
            usage["input_tokens"] += int(u.get("input_tokens") or 0)
            usage["output_tokens"] += int(u.get("output_tokens") or 0)
            return _extract_text(resp)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            usage["errors"] += 1
            # 429/5xx/网络抖动 → 退避重试；4xx 其他 → 快速失败
            code = getattr(e, "code", None)
            if code is not None and 400 <= code < 500 and code != 429:
                raise RuntimeError(f"LLM 4xx: {e}") from e
            wait = 2 ** attempt * 3
            time.sleep(wait)
    raise RuntimeError(f"LLM 调用失败（重试 {retries} 次后放弃）: {last_err}")


def _extract_text(resp: dict) -> str:
    content = resp.get("content")
    if isinstance(content, str):
        # 个别兼容端直接返回字符串
        if content.startswith("[") and content.strip().endswith("]"):
            try:
                arr = json.loads(content)
                return "".join(b.get("text", "") for b in arr if isinstance(b, dict))
            except json.JSONDecodeError:
                return content
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def extract_json(text: str, *, first: bool = True) -> dict | list | None:
    """从 LLM 文本中提取 JSON（剥掉 ```json 围栏与思考残余）。

    默认取第一个 JSON 值；first=False 时取最后一个（数组场景）。
    """
    t = re.sub(r"```(?:json)?", "", text)
    # 找所有平衡的 JSON 值起点
    candidates = []
    for m in re.finditer(r"[\[{]", t):
        depth = 0
        in_str = False
        esc = False
        for i in range(m.start(), len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    candidates.append(t[m.start() : i + 1])
                    break
    if not candidates:
        # 退化：直接正则贪婪抓取（多行）
        m = re.search(r"(\{.*\}|\[.*\])", t, re.DOTALL)
        candidates = [m.group(0)] if m else []
    picks = candidates[::-1] if not first else candidates
    for c in picks:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


if __name__ == "__main__":
    r = chat("只回复一个字：好", max_tokens=16)
    print("raw:", r, "| usage:", json.dumps(USAGE, ensure_ascii=False))