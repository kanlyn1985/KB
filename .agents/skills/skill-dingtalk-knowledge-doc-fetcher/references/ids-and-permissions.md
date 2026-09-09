# IDs and Permissions

Use this reference when a DingTalk knowledge document fetch fails or when an identifier is ambiguous.

## Identifier Map

| Name | Meaning | Source | Common Mistake |
|------|---------|--------|----------------|
| `appKey` | DingTalk app credential ID | App management page | Passing it as token |
| `appSecret` | DingTalk app credential secret | App management page | Writing it to logs |
| `accessToken` | Short-lived API token | `/v1.0/oauth2/accessToken` | Reusing after expiry |
| `corpId` | Tenant/corporation ID | DingTalk app/org context | Treating it as app key or operator ID |
| `operatorId` | Operator identity, usually `unionId` | User lookup / caller context | Passing `userId` when API expects `unionId` |
| `workspaceId` | Knowledge-base space ID | `mineWorkspaces` or workspace API | Passing it as folder/node ID |
| `rootNodeId` | Root node for traversal | `mineWorkspaces` | Calling blocks with it |
| `nodeId` | Knowledge node/document/folder ID | `nodes`, `queryByUrl`, document URL | Assuming every node has body content |
| `docKey` | Online document key for doc APIs | Node response or doc URL parsing | Using folder node ID |

## Permission Checklist

For API access:

- The app must have the required wiki/document read scopes in DingTalk developer console.
- Listing and fetching workspaces requires `Wiki.Workspace.Read`.
- Traversing knowledge-base nodes requires `Wiki.Node.Read`.
- Reading document/file blocks can require `Storage.File.Read`.
- Exporting online spreadsheets (`axls`) through workbook APIs requires `Document.Workbook.Read`.
- The operator must have permission to access the target knowledge base and document.
- The target document may have separate node-level permissions even when the workspace is visible.

For common errors:

- HTTP 401: token missing, expired, or generated for the wrong app.
- HTTP 403: app scope missing, operator lacks access, or document permission is restricted.
- HTTP 400: wrong ID type, invalid URL, missing `operatorId`, or using a folder/root node as a document.
- HTTP 500 with `Target document should be doc.`: the node is likely `axls`, `able`, PDF, HTML, or another non-`adoc` file; do not read it with document blocks.
- HTTP 403 requiring `Document.Workbook.Read`: the node is an online spreadsheet (`axls`) and the app needs the workbook read scope before `.xlsx` export can continue.
- Empty children list: wrong `parentNodeId`, no permission, or the folder is genuinely empty.
- Blocks endpoint returns not found: try `docKey` from `queryByUrl`; do not assume `rootNodeId` is readable as a document.

## Resolve Operator unionId

The document APIs usually require `operatorId=<unionId>`. If the user does not
know the unionId:

1. If they know the DingTalk `userid`, call user detail and read `result.unionid`.
2. If they only know the mobile number, call mobile lookup to get `userid`, then
   call user detail to get `unionid`.

Script helpers:

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py \
  --lookup-userid-by-mobile "<mobile>"

python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py \
  --lookup-unionid-by-userid "<userid>"
```

Both helpers are read-only. They still require a valid app token or
`DINGTALK_APP_KEY/DINGTALK_APP_SECRET`.

## URL Handling

Supported useful URL patterns include:

- `https://alidocs.dingtalk.com/i/nodes/{nodeId}`
- `https://alidocs.dingtalk.com/i/spaces/{workspaceId}/overview`
- `https://alidocs.dingtalk.com/document/edit?...&dentryKey=...`
- `https://alidocs.dingtalk.com/document/preview?...&dentryKey=...`

Prefer `queryByUrl` for URL resolution because DingTalk URL formats vary. Regex extraction is only a fallback for obvious `/i/nodes/<id>` links.
For `/i/spaces/{workspaceId}/overview`, treat the URL segment as a URL slug first. Match it against `GET /v2.0/wiki/workspaces` response `url`, then use the response `workspaceId/rootNodeId`; do not call document blocks with either workspace identifier.

## Security Rules

- Never commit `appSecret`, `accessToken`, or `.env`.
- Prefer `.env` or shell environment variables over command history for secrets.
- When showing examples to users, mask secrets.
- This skill is read-only; do not add write/delete/move/permission APIs unless the user explicitly asks for a separate skill expansion.
