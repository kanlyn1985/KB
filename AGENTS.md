# AGENTS

## Repository layout

- `agent_kb_core/` — the active project: the `agent_kb` package, Web UI, and the landing/eval tooling. See `agent_kb_core/README.md`.
- `docs/ontology/` — the RFLP ontology layer: tree skeleton, document-landing data, node cards, golden cases, and query-understanding design.
- `corpus/` — source document corpus (standards PDFs, requirements xlsx/docx, the Athena team corpus).
- `archive/` — superseded work, kept for reference only: the legacy `enterprise_agent_kb` pipeline outputs and the old `kb1_ontology` design.

## Development rules

- Keep the data model traceable from `evidence` to `facts` to ontology nodes.
- Prefer additive schema changes with migrations instead of destructive resets.
- Preserve quality metadata across every processing stage.
- Build for single-node execution first; do not introduce distributed dependencies prematurely.

## Module ownership (package `agent_kb`)

- `agent_kb.cli` / `agent_kb.platform_cli` / `agent_kb.recovery_cli` / `agent_kb.worker_cli`: operator-facing commands
- `agent_kb.core`: document intake, evidence, semantic units, facts
- `agent_kb.domains`: domain pack loading and schema
- `agent_kb.query`: query understanding (rule + LLM hybrid)
- `agent_kb.retrieval`: multi-channel retrieval, fusion, cards, reranking
- `agent_kb.pipeline`: document → context-pack compilation
- `agent_kb.storage`: SQLite connectivity, migrations, backup/recovery
- `agent_kb.service` / `agent_kb.security`: HTTP API, auth/RBAC/audit
- `agent_kb.adapters`: OpenAPI, MCP, client codegen
- `agent_kb.observability` / `agent_kb.runtime`: metrics/telemetry, jobs/leadership/rate limiting

## Embedding operations (build remote, query local) — 2026-08-28 约定

两条固定链路，按任务类型选择：

### 重建索引（批量嵌入，31557+ 条）→ 远程机
- 远程 `evt@100.72.228.67`（Tailscale），Ollama 模型 `qllama/bge-small-zh-v1.5`（= BAAI/bge-small-zh-v1.5，512 维）；
- 流程：打包源码+数据 → scp → 远程本地跑 `import-node-cards --remote-embedding`
  （连 `http://127.0.0.1:11434`，**不经过隧道**，31557 条 ~10 分钟）；
- 回传：**只传向量**（`provider_id LIKE 'remote-json%'` 的行导出 JSONL、向量 round 5 位小数、gzip
  ~40MB，~15 分钟），不传整库；本机用 upsert 脚本并入现有 DB（source_id 100% 对齐校验）；
- 教训：不要通过 SSH 隧道跑批量嵌入（DERP 带宽 ~50-65KB/s，320MB 向量数据必死）；
  ssh 隧道会随机断（Connection reset by peer），任何长任务必须预热缓存后离线跑。

### 本地查询（单条嵌入）→ 本机嵌入服务
- 服务：`python agent_kb_core/tools/local_embed_server.py --port 11500`（fastembed ONNX，
  模型缓存 `~/.fastembed_cache`，加载 1.7s，17ms/条）；
- 客户端：`AGENT_KB_EMBEDDING_URL=http://127.0.0.1:11500/v1/embeddings`、
  `AGENT_KB_EMBEDDING_MODEL=qllama/bge-small-zh-v1.5`（**MODEL 名必须保持 qllama/ 前缀**
  ——provider_id `remote-json:qllama/bge-small-zh-v1.5:512` 要与库内 31557 条向量的
  provider_id 一致，否则向量通道按 provider 过滤静默归零）、
  `AGENT_KB_EMBEDDING_DIMENSIONS=512`；
- 热查询端到端 ~2s（嵌入 17ms + numpy 矩阵缓存毫秒级 + 内存基线 ~1s）。

### 注意事项
- 向量矩阵缓存在 `SQLiteVectorIndex` 类级（键含 db 路径/provider/维度/行数），写索引后自动失效；
  环境变量 `AGENT_KB_VECTOR_NO_NUMPY=1` 可强制回退纯 Python 路径（慢 ~20s，仅排障用）；
- 本地服务常驻时查询才可用；服务未起时 `--remote-embedding` 查询会连接失败，
  此时要么起服务要么去掉该 flag 走 hash 通道。