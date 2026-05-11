# Attention

本文件是 CodeStable 技能启动必读的项目注意事项入口。所有 CodeStable 子技能开始工作前必须读取它。

## 项目碎片知识

<!-- cs-note managed: 用 cs-note 维护，新条目按下面分节追加 -->

### 编译与构建

### 运行与本地起服务
- 项目工作目录固定为 `E:\AI_Project\opencode_workspace\KB1`。
- 知识库运行根目录是 `knowledge_base`，CLI 需要显式传 `--root knowledge_base`。
- 本地 API 启动命令：
  `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base serve-api --host 127.0.0.1 --port 8000`
- API 健康检查：
  `http://127.0.0.1:8000/health`

### 测试
- 快速回归优先跑：
  `C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q`
- 带 `-k` 过滤时，pytest 输出大量 `deselected` 是正常现象，表示未匹配过滤表达式的测试被跳过。

### 命令与脚本陷阱
- `query-context` 和 `answer-query` 的查询文本必须使用 `--query` 参数，不能作为位置参数传入。
- PowerShell here-string 直接写中文有时会变成 `????`；HTTP 或 Python 脚本验证中文查询时优先使用 Unicode escape 字符串。
- 短缩写定义问题如 `CP是什么意思`、`CC是什么意思` 应先走歧义澄清或规则扩写，不应先交给 LLM 扩写。

### 路径与目录约定
- 源码目录：`src\enterprise_agent_kb`。
- SQLite 和生成知识库资产位于 `knowledge_base`。
- CodeStable 文档入口位于 `.codestable`，旧文档暂不移动，迁移需用户逐项确认。

### 环境变量与凭证
- Advanced Query Planner 默认关闭；需要实验链路时设置 `EAKB_ENABLE_ADVANCED_QUERY_PLANNER=1`。

### 其他
