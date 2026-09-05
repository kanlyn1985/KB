# API Flow

Use this reference when fetching DingTalk knowledge-base document content through OpenAPI.

## 0. Required Inputs

- App credential: `appKey` and `appSecret`.
- Operator: `operatorId`, normally the operator user's `unionId`.
- Target: one of:
  - an `alidocs.dingtalk.com` URL;
  - a knowledge space URL like `https://alidocs.dingtalk.com/i/spaces/{workspaceId}/overview`;
  - a known `workspaceId/rootNodeId`;
  - a known document `nodeId` or `docKey`.

Do not invent any ID. Read it from the user, the URL parsing response, or a previous API response.

## 1. Get Access Token

Endpoint:

```text
POST https://api.dingtalk.com/v1.0/oauth2/accessToken
```

Body:

```json
{
  "appKey": "<appKey>",
  "appSecret": "<appSecret>"
}
```

Use the returned `accessToken` in:

```text
x-acs-dingtalk-access-token: <accessToken>
```

If the user already has a valid DingTalk OpenAPI token, pass it as `--access-token`
or `DINGTALK_ACCESS_TOKEN` and skip this step.

## 2. Get My Document Knowledge Base

Endpoint:

```text
GET https://api.dingtalk.com/v2.0/wiki/mineWorkspaces?operatorId=<unionId>
```

Expected useful fields:

- `workspaceId`: knowledge-base space ID.
- `rootNodeId`: root node for traversal.
- `name` / `workspaceName`: display name if present.

This call does not return document body content.

## 3. Locate a Node

### From an alidocs URL

Endpoint:

```text
POST https://api.dingtalk.com/v2.0/wiki/nodes/queryByUrl?operatorId=<unionId>
```

Body:

```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/xxx",
  "option": {
    "withStatisticalInfo": true,
    "withPermissionRole": true
  }
}
```

Use the returned `nodeId`, `docKey`, `contentType`, `category`, `type`, and URL fields to decide the next step.

### By traversing children

Endpoint:

```text
GET https://api.dingtalk.com/v2.0/wiki/nodes?parentNodeId=<nodeId>&maxResults=50&operatorId=<unionId>
```

For a space overview URL, first extract the URL slug from:

```text
https://alidocs.dingtalk.com/i/spaces/{workspaceId}/overview
```

Important: the slug in the URL can differ from the OpenAPI `workspaceId`. Prefer
`GET /v2.0/wiki/workspaces` and match the returned `url`, then use that record's
`workspaceId` and `rootNodeId`.

To fetch one workspace:

```text
GET https://api.dingtalk.com/v2.0/wiki/workspaces/{workspaceId}?withPermissionRole=false&operatorId=<unionId>
```

The response contains `workspace.rootNodeId`. Use that value as `parentNodeId`
for `/v2.0/wiki/nodes`.

If pagination fields such as `nextToken` or `hasMore` are returned, continue until exhausted or until the target is found.

Node routing:

- Folder-like node: list children.
- DingTalk text document node, normally extension `adoc`: read document blocks.
- Online spreadsheets (`axls`) are not readable through the doc blocks endpoint; export them through the workbook APIs.
- AI tables (`able`) are not readable through the doc blocks endpoint; use a future aitable-specific export workflow.
- Binary or other file nodes: this skill stops at metadata; use a drive/file download workflow instead.

## 4. Export Online Spreadsheets

Only use this for DingTalk online spreadsheets with extension `axls`.

Endpoint sequence:

```text
GET https://api.dingtalk.com/v1.0/doc/workbooks/{workbookId}/sheets?operatorId=<unionId>
GET https://api.dingtalk.com/v1.0/doc/workbooks/{workbookId}/sheets/{sheetId}?operatorId=<unionId>
GET https://api.dingtalk.com/v1.0/doc/workbooks/{workbookId}/sheets/{sheetId}/ranges/{rangeAddress}?operatorId=<unionId>&select=values,formulas,displayValues
```

Use the node `nodeId` as `workbookId` for `axls` knowledge-base nodes. Read each
worksheet's `lastNonEmptyRow` and `lastNonEmptyColumn`, then fetch `A1:<lastCell>`.
The bundled script writes the returned values/formulas/display values into a local
`.xlsx` file with one Excel sheet per DingTalk worksheet.

Current limitations:

- The direct range-read export focuses on cell content. Server-side export may preserve
  more formatting, merge state, comments, images, and charts, but that export API is not
  bundled in this script yet.
- `able` AI tables are only counted/identified for now.
- Permission failures usually require `Document.Workbook.Read`.

Script usage:

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py \
  --url "https://alidocs.dingtalk.com/i/spaces/<space-slug>/overview" \
  --crawl \
  --include-spreadsheets \
  --output-dir "deliverables/dingtalk_kb"
```

## 5. Read Document Blocks

Endpoint shape:

```text
GET https://api.dingtalk.com/v1.0/doc/suites/documents/{docKey}/blocks?operatorId=<unionId>
```

Use the best available document identifier from the node response:

1. `docKey`
2. `nodeId`
3. a stable document key extracted by DingTalk from the URL

The response is structured blocks, not Markdown. Always keep the raw JSON when fidelity matters.
If the API returns `Target document should be doc.`, the node is usually not an `adoc` text document.

## 6. Convert Blocks to Text

For summaries or downstream processing:

1. Sort blocks by `index`, `sequence`, or returned order.
2. Extract visible text from paragraph, heading, list, table, code, and text-run fields.
3. Preserve tables as Markdown tables only when cell boundaries are clear.
4. Render attachment blocks as traceable placeholders using `resourceId`.
5. Keep unknown blocks as comments or JSON snippets in the raw output rather than dropping them silently.

Current script behavior:

- `heading`, `paragraph`, `table`, `blockquote`: converted to Markdown.
- `attachment`: converted to `[附件: name](dingtalk-resource://resourceId)`; image MIME attachments use Markdown image syntax.
- `unknown`: converted to an HTML comment with block id. In observed responses, some embedded visual content is returned this way without a download URL.

## 7. Minimal curl Sequence

```bash
curl --location 'https://api.dingtalk.com/v1.0/oauth2/accessToken' \
  --header 'Content-Type: application/json' \
  --data '{"appKey":"<appKey>","appSecret":"<appSecret>"}'

curl --location 'https://api.dingtalk.com/v2.0/wiki/mineWorkspaces?operatorId=<unionId>' \
  --header 'x-acs-dingtalk-access-token: <accessToken>'

curl --location 'https://api.dingtalk.com/v2.0/wiki/nodes?parentNodeId=<rootNodeId>&maxResults=50&operatorId=<unionId>' \
  --header 'x-acs-dingtalk-access-token: <accessToken>'

curl --location 'https://api.dingtalk.com/v1.0/doc/suites/documents/<docKey>/blocks?operatorId=<unionId>' \
  --header 'x-acs-dingtalk-access-token: <accessToken>'
```
