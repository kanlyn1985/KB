# KB1 团队查询入口（三步启动）

> ⚠️ 当前无鉴权，仅限 Tailscale 内网使用。请勿暴露到公网。

## 第 1 步：启动本机嵌入服务（每台机器一次/开机后）

```powershell
cd E:\AI_Project\opencode_workspace\KB1
python agent_kb_core\tools\local_embed_server.py --port 11500
```

看到 `model ready` 即可（窗口保持开着，约 100MB 内存）。

## 第 2 步：启动知识库 Web UI

```powershell
cd E:\AI_Project\opencode_workspace\KB1
python agent_kb_core\webui\server.py --db agent_kb_core\validation\node-index.sqlite3 --domain-dir agent_kb_core\domains\obc_dcdc
```

启动日志出现 `[webui] 语义通道已启用: remote-json:qllama/bge-small-zh-v1.5:512` 说明全通道检索就绪。

## 第 3 步：同事访问

浏览器打开 `http://<你的机器Tailscale IP>:8080`（`tailscale ip -4` 查询）。

## 常见问题

- **日志显示"语义通道不可用"**：第 1 步服务没起，或端口不是 11500。此时仍可查询（退化为 hash 通道，召回质量下降）。
- **只想本机自己用**：启动时加 `--host 127.0.0.1`。
- **想关闭语义通道**：加 `--no-embedding`。
- **查询慢（>10s）**：首查询需构建向量缓存（~13s），之后恢复正常；持续慢请联系管理员。