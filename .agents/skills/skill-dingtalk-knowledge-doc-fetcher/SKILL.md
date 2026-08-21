---
name: skill-dingtalk-knowledge-doc-fetcher
description: "钉钉知识库文档内容获取技能。TRIGGER when: 用户要通过钉钉开放平台 API 获取知识库、我的文档、知识库节点、alidocs 链接、钉钉文档正文、doc blocks、或把知识库文档导出为 Markdown/JSON，把在线电子表格 axls 导出为 Excel/xlsx。DO NOT TRIGGER when: 用户只是要管理知识库成员/权限、创建或编辑钉钉文档、操作 AI 表格/钉盘文件、或使用 dws 连接器直接读取在线文档。"
---

# 钉钉知识库文档获取

通过钉钉 OpenAPI 读取知识库中的文档内容。核心边界：

- 知识库空间信息走 `wiki` API，只能拿 `workspaceId`、`rootNodeId`、节点元数据。
- 文档正文走 `doc` API 的 blocks 接口，不在 `wiki` 节点详情里。
- 本技能只读不写，不执行删除、移动、授权、创建、编辑等操作。

## 工作流选择

用户只有应用凭据和操作人：

1. 读 [references/api-flow.md](references/api-flow.md)。
2. 先获取 `accessToken`。
3. 调 `mineWorkspaces` 拿 `workspaceId/rootNodeId`。
4. 遍历节点，定位目标文档。
5. 调文档 blocks 接口读取正文。

用户提供了 `alidocs.dingtalk.com` 文档链接：

1. 读 [references/api-flow.md](references/api-flow.md) 和 [references/ids-and-permissions.md](references/ids-and-permissions.md)。
2. 用 `queryByUrl` 把链接解析为节点。
3. 若节点是在线文档，读取 blocks；若是文件夹，继续列子节点。

用户提供了 `https://alidocs.dingtalk.com/i/spaces/{workspaceId}/overview` 知识库链接：

1. 读 [references/api-flow.md](references/api-flow.md) 和 [references/ids-and-permissions.md](references/ids-and-permissions.md)。
2. 从 URL 提取 `workspaceId`。
3. 先尝试按 workspace 根目录列节点。
4. 若租户接口不支持 workspace 直列，要求补充 `rootNodeId` 或改用具体文档 URL。

用户遇到 401/403/400、`docKey` 不确定、`operatorId` 不确定：

1. 读 [references/ids-and-permissions.md](references/ids-and-permissions.md)。
2. 明确区分 `appKey/appSecret`、`accessToken`、`unionId`、`userId`、`workspaceId`、`rootNodeId`、`nodeId/docKey`。
3. 不要猜 ID；从接口返回或用户给的链接中提取。

## 可执行脚本

优先使用脚本做只读获取：

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py --help
```

示例：

```bash
# 从链接读取正文，输出 Markdown 和原始 blocks JSON
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --url "https://alidocs.dingtalk.com/i/nodes/xxx" ^
  --operator-union-id "<unionId>" ^
  --output "deliverables/dingtalk_doc.md" ^
  --raw-output "deliverables/dingtalk_doc.blocks.json"

# 列出“我的文档”知识库根目录节点
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --operator-union-id "<unionId>" ^
  --list-root

# 从知识库 space 链接递归拉取文档内容
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --url "https://alidocs.dingtalk.com/i/spaces/<workspaceId>/overview" ^
  --access-token "<accessToken>" ^
  --operator-union-id "<unionId>" ^
  --crawl ^
  --output-dir "deliverables/dingtalk_kb"

# 已知文档 nodeId/docKey 时直接读正文
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --doc-key "<nodeId-or-docKey>" ^
  --operator-union-id "<unionId>" ^
  --format json

# 只知道手机号时，先查 userid
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --lookup-userid-by-mobile "<mobile>"

# 已知 userid 时，再查 unionId
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --lookup-unionid-by-userid "<userid>"
```

导出知识库里的在线电子表格（`.axls`）为 Excel：

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py ^
  --url "https://alidocs.dingtalk.com/i/spaces/<space-slug>/overview" ^
  --crawl ^
  --include-spreadsheets ^
  --output-dir "deliverables/dingtalk_kb"
```

表格导出说明：

- `--include-spreadsheets` 的别名是 `--include-tables`。
- `.axls` 会输出到 `--output-dir` 下的 `spreadsheets/*.xlsx`。
- 钉钉里的每个工作表会保存成 Excel 里的一个 worksheet。
- 应用需要开通 `Document.Workbook.Read`，否则工作簿接口会返回 HTTP 403。
- AI 表格 / 多维表节点（`.able`）当前只识别和计数，后续再接专用导出。

凭据优先从参数读取，其次从环境变量或仓库根目录 `.env` 读取：

- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`
- `DINGTALK_ACCESS_TOKEN` 或 `DINGTALK_API_TOKEN`（已有 token 时可跳过 appKey/appSecret）
- `DINGTALK_OPERATOR_UNION_ID`
- `DINGTALK_CORP_ID`（可选，仅用于诊断记录）

## 输出判断

- 成功读正文：报告输出文件、文档标题、blocks 数量。
- Markdown 转换支持 `heading`、`paragraph`、`table`、`blockquote`、`attachment` 占位。
- 在线电子表格导出支持 `.axls`，输出为 `.xlsx`。
- `attachment` 会输出 `dingtalk-resource://<resourceId>` 占位；当前不自动下载附件。
- `unknown` 块会输出 HTML 注释标记。若原文这里是图片，说明 blocks 接口没有返回可下载图片元数据，需要后续接入附件下载或文档导出方案。
- 只拿到节点：说明该节点类型，并提示是否继续读取子节点或正文。
- 权限失败：报告接口名、HTTP 状态码、钉钉错误码/消息，以及缺失 scope 或操作者权限线索。
- blocks 转 Markdown 不完整：保留原始 JSON，并说明需要基于真实 block schema 增补转换规则。

## Theia 审查任务钉钉通知

本技能现补充 Theia 审查任务完成通知能力。审查任务 `succeeded` 或 `failed`
后，可通过钉钉内部应用工作通知发送 Markdown 消息给任务发起人与管理员。

配置与调试说明见 [references/task-notification.md](references/task-notification.md)。

快速 dry-run：

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/send_dingtalk_work_notice.py ^
  --status succeeded ^
  --task-id demo001 ^
  --project-id P202503011 ^
  --audit-type asw40_platform_standard_audit ^
  --audit-label "ASW4.0平台需求标准化审查" ^
  --created-by 002881CE ^
  --message "审查已完成" ^
  --dry-run
```
