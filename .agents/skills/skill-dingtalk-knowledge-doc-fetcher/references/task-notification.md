# DingTalk Task Notification

Use this reference when Theia audit tasks should send DingTalk work notifications
after a task succeeds or fails.

## Required App Capability

The notifier supports two channels.

### Work notification

This channel uses the DingTalk internal-app work notification API:

```text
POST https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2
```

Required configuration:

- `DINGTALK_NOTIFY_ENABLED=1`
- `DINGTALK_AGENT_ID=<internal app agentId>`
- `DINGTALK_APP_KEY=<appKey>` and `DINGTALK_APP_SECRET=<appSecret>`, or an existing `DINGTALK_ACCESS_TOKEN`

The app must have permission to send enterprise work notifications.
`DINGTALK_AGENT_ID` must be the numeric AgentId from the DingTalk internal app
detail page. It is not the appKey, clientId, corpId, unionId, or robot webhook
access token.

### App robot one-to-one message

This channel uses the DingTalk app robot one-to-one API:

```text
POST https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend
```

Required configuration:

- `DINGTALK_NOTIFY_ENABLED=1`
- `DINGTALK_NOTIFY_CHANNEL=robot_oto`
- `DINGTALK_ROBOT_CODE=<robotCode>`
- `DINGTALK_APP_KEY=<appKey>` and `DINGTALK_APP_SECRET=<appSecret>`, or an existing `DINGTALK_ACCESS_TOKEN`

The app must enable robot capability and have the permission to send internal
robot messages. Recipients are still DingTalk `userid` values; unionId values can
be configured with `DINGTALK_NOTIFY_ADMIN_UNIONIDS` and are resolved through
DingTalk OAPI before sending.

## Recipients

Theia sends notifications to:

- the task creator, from `task.created_by`;
- Theia admins, from `THEIA_ADMINS` or `outputfile/admin_users.json`;
- optional fixed DingTalk users from `DINGTALK_NOTIFY_EXTRA_USERIDS` or `DINGTALK_NOTIFY_ADMIN_USERIDS`.

If the Polarion/Theia user ID is not the same as the DingTalk `userid`, provide a map:

```json
{
  "002881CE": "ding-userid-1",
  "003900CE": "ding-userid-2"
}
```

Default map file path:

```text
inputfile/dingtalk_userid_map.json
```

Or set:

```text
DINGTALK_USERID_MAP_FILE=path/to/map.json
DINGTALK_USERID_MAP={"002881CE":"ding-userid-1"}
```

By default, when no mapping is found, the notifier assumes the Theia user ID can
also be used as DingTalk `userid`. Disable that fallback with:

```text
DINGTALK_NOTIFY_ASSUME_USERID=0
```

## Report Link

Set `THEIA_PUBLIC_BASE_URL` to include a clickable report link in the DingTalk
message:

```text
THEIA_PUBLIC_BASE_URL=http://theia.example.com
```

The generated link points to:

```text
/theia/?project_id=<project_id>&audit_type=<audit_type>&view=report
```

## Manual Test

Dry-run message rendering without sending:

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/send_dingtalk_work_notice.py \
  --status succeeded \
  --task-id demo001 \
  --project-id P202503011 \
  --audit-type asw40_platform_standard_audit \
  --audit-label "ASW4.0平台需求标准化审查" \
  --created-by 002881CE \
  --message "审查已完成" \
  --dry-run
```

Send a real notification after the environment variables above are configured:

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/send_dingtalk_work_notice.py \
  --status failed \
  --task-id demo002 \
  --project-id P202503011 \
  --audit-type sw_requirement_standard \
  --audit-label "软件需求标准化审查" \
  --created-by 002881CE \
  --message "审查执行失败" \
  --error "example failure" \
  --admin-ids "002881CE"
```

Robot one-to-one test:

```bash
python skill/skill-dingtalk-knowledge-doc-fetcher/scripts/send_dingtalk_work_notice.py \
  --channel robot_oto \
  --robot-code ding1kqh9f1thsvh83bg \
  --status succeeded \
  --task-id demo-robot \
  --project-id P202503011 \
  --audit-type asw40_platform_standard_audit \
  --audit-label "ASW4.0平台需求标准化审查" \
  --admin-unionids "LQmjFlWjiigGtviSg237krswiEiE" \
  --message "机器人单聊发送测试"
```

Notification failures are recorded on the task as `dingtalk_notification` and do
not change the audit task status.
