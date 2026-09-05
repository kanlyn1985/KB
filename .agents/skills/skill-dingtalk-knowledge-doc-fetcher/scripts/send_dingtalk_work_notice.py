#!/usr/bin/env python3
"""Send DingTalk work notifications for Theia audit task results."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fetch_dingtalk_knowledge_doc import DingTalkError, get_access_token, load_dotenv, request_json, request_oapi_json


DEFAULT_USERID_MAP_FILE = "inputfile/dingtalk_userid_map.json"
DEFAULT_UNIONID_MAP_FILE = "inputfile/dingtalk_unionid_map.json"
DEFAULT_DEPARTMENT_MEMBERS_FILE = "inputfile/dingtalk_software_department_members.json"


class DingTalkNotifyError(RuntimeError):
    pass


def _split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = str(value).replace(";", ",").split(",")
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _truthy_env(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _load_json_map(value: str) -> dict[str, str]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        data = {}
        for part in _split_csv(value):
            if ":" in part:
                key, mapped = part.split(":", 1)
            elif "=" in part:
                key, mapped = part.split("=", 1)
            else:
                continue
            data[key.strip()] = mapped.strip()
    if not isinstance(data, dict):
        return {}
    return {str(key).strip().upper(): str(mapped).strip() for key, mapped in data.items() if str(key).strip() and str(mapped).strip()}


def _resolve_repo_file(repo_root: Path, path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = repo_root / path
    return path


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_first(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(record.get(key, "") or "").strip()
        if value:
            return value
    return ""


def load_department_member_maps(repo_root: Path) -> dict[str, dict[str, str]]:
    member_file = os.getenv("DINGTALK_DEPARTMENT_MEMBERS_FILE", DEFAULT_DEPARTMENT_MEMBERS_FILE).strip()
    if not member_file:
        return {"employee_to_userid": {}, "name_to_userid": {}, "unionid_to_userid": {}, "employee_to_display": {}}
    path = _resolve_repo_file(repo_root, member_file)
    if not path.exists():
        return {"employee_to_userid": {}, "name_to_userid": {}, "unionid_to_userid": {}, "employee_to_display": {}}

    try:
        data = _load_json_file(path)
    except Exception as exc:
        raise DingTalkNotifyError(f"Failed to read DingTalk department members {path}: {exc}") from exc

    if isinstance(data, dict):
        records = data.get("members") or data.get("employees") or data.get("data") or []
    else:
        records = data
    if not isinstance(records, list):
        return {"employee_to_userid": {}, "name_to_userid": {}, "unionid_to_userid": {}, "employee_to_display": {}}

    employee_to_userid: dict[str, str] = {}
    name_to_userid: dict[str, str] = {}
    unionid_to_userid: dict[str, str] = {}
    employee_to_display: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        employee_id = _pick_first(record, ("工号", "employee_id", "job_number", "staff_id", "work_no")).upper()
        userid = _pick_first(record, ("userid", "userId", "user_id", "staffId", "staff_id"))
        unionid = _pick_first(record, ("unionid", "unionId", "union_id"))
        name = _pick_first(record, ("姓名", "name", "username", "display_name"))

        if employee_id and userid:
            employee_to_userid[employee_id] = userid
        if name and userid:
            name_to_userid[name] = userid
            name_to_userid[name.upper()] = userid
        if unionid and userid:
            unionid_to_userid[unionid] = userid
            unionid_to_userid[unionid.upper()] = userid
        if employee_id:
            employee_to_display[employee_id] = f"{name}({employee_id})" if name else employee_id
    return {
        "employee_to_userid": employee_to_userid,
        "name_to_userid": name_to_userid,
        "unionid_to_userid": unionid_to_userid,
        "employee_to_display": employee_to_display,
    }


def load_userid_map(repo_root: Path) -> dict[str, str]:
    department_maps = load_department_member_maps(repo_root)
    result = dict(department_maps["employee_to_userid"])
    result.update(department_maps["name_to_userid"])
    result.update(_load_json_map(os.getenv("DINGTALK_USERID_MAP", "")))
    map_file = os.getenv("DINGTALK_USERID_MAP_FILE", DEFAULT_USERID_MAP_FILE).strip()
    if map_file:
        path = _resolve_repo_file(repo_root, map_file)
        if path.exists():
            try:
                file_data = _load_json_file(path)
            except Exception as exc:
                raise DingTalkNotifyError(f"Failed to read DingTalk userid map {path}: {exc}") from exc
            if isinstance(file_data, dict):
                result.update(
                    {
                        str(key).strip().upper(): str(value).strip()
                        for key, value in file_data.items()
                        if str(key).strip() and str(value).strip()
                    }
                )
    return result


def load_unionid_map(repo_root: Path) -> dict[str, str]:
    result = dict(load_department_member_maps(repo_root)["unionid_to_userid"])
    result.update(_load_json_map(os.getenv("DINGTALK_UNIONID_USERID_MAP", "")))
    map_file = os.getenv("DINGTALK_UNIONID_MAP_FILE", DEFAULT_UNIONID_MAP_FILE).strip()
    if map_file:
        path = _resolve_repo_file(repo_root, map_file)
        if path.exists():
            try:
                file_data = _load_json_file(path)
            except Exception as exc:
                raise DingTalkNotifyError(f"Failed to read DingTalk unionid map {path}: {exc}") from exc
            if isinstance(file_data, dict):
                result.update(
                    {
                        str(key).strip(): str(value).strip()
                        for key, value in file_data.items()
                        if str(key).strip() and str(value).strip()
                    }
                )
    return result


def resolve_access_token_from_env() -> str:
    existing_token = os.getenv("DINGTALK_ACCESS_TOKEN") or os.getenv("DINGTALK_API_TOKEN")
    if existing_token:
        return existing_token
    app_key = os.getenv("DINGTALK_APP_KEY", "").strip()
    app_secret = os.getenv("DINGTALK_APP_SECRET", "").strip()
    if app_key and app_secret:
        return get_access_token(app_key, app_secret)
    raise DingTalkNotifyError("Missing DINGTALK_ACCESS_TOKEN or DINGTALK_APP_KEY/DINGTALK_APP_SECRET.")


def get_userid_by_unionid(token: str, unionid: str) -> str:
    payload = request_oapi_json(
        "POST",
        "/topapi/user/getbyunionid",
        token,
        body={"unionid": unionid},
    )
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    userid = str(result.get("userid") or payload.get("userid") or "").strip()
    if not userid:
        raise DingTalkNotifyError(f"userid missing for unionid {unionid}: {json.dumps(payload, ensure_ascii=False)[:500]}")
    return userid


def resolve_unionids_to_userids(unionids: list[str], token: str, repo_root: Path) -> list[str]:
    unionid_map = load_unionid_map(repo_root)
    resolved: list[str] = []
    seen: set[str] = set()
    for unionid in unionids:
        userid = unionid_map.get(unionid) or unionid_map.get(unionid.upper())
        if not userid:
            userid = get_userid_by_unionid(token, unionid)
        if userid and userid not in seen:
            resolved.append(userid)
            seen.add(userid)
    return resolved


def _identifier_candidates(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    candidates: list[str] = []
    for segment in re.split(r"[,，、;；\n\r\t]+", text):
        segment = segment.strip()
        if not segment:
            continue
        for part in re.split(r"[()（）]", segment):
            part = part.strip()
            if part and part not in candidates:
                candidates.append(part)
        if segment not in candidates:
            candidates.append(segment)
    if text not in candidates and len(candidates) <= 1:
        candidates.append(text)
    return candidates


def resolve_recipient_userids(
    task: dict[str, Any],
    admin_ids: list[str] | set[str] | tuple[str, ...] | None,
    repo_root: Path,
    unionids: list[str] | set[str] | tuple[str, ...] | None = None,
    token: str | None = None,
) -> list[str]:
    userid_map = load_userid_map(repo_root)
    assume_same_userid = _truthy_env("DINGTALK_NOTIFY_ASSUME_USERID", "1")

    identifiers: list[str] = []
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    is_aitable_task = source.get("type") == "dingtalk_aitable"
    if is_aitable_task:
        identifiers.extend(_identifier_candidates(source.get("review_admin_display", "")))
        identifiers.extend(_identifier_candidates(source.get("requested_by_display", "")))
        identifiers.extend(_identifier_candidates(task.get("created_by_display", "")))
        identifiers.extend(_identifier_candidates(task.get("created_by", "")))
    else:
        identifiers.extend(_identifier_candidates(task.get("created_by", "")))
        identifiers.extend(_identifier_candidates(source.get("requested_by_display", "")))
        identifiers.extend(_identifier_candidates(task.get("created_by_display", "")))

    include_theia_admins = _truthy_env("DINGTALK_NOTIFY_INCLUDE_THEIA_ADMINS", "1")
    if include_theia_admins:
        identifiers.extend(_split_csv(admin_ids or []))

    direct_userids = _split_csv(os.getenv("DINGTALK_NOTIFY_EXTRA_USERIDS"))
    direct_unionids = _split_csv(os.getenv("DINGTALK_NOTIFY_EXTRA_UNIONIDS"))
    if include_theia_admins:
        direct_userids += _split_csv(os.getenv("DINGTALK_NOTIFY_ADMIN_USERIDS"))
        direct_unionids += _split_csv(unionids or []) + _split_csv(os.getenv("DINGTALK_NOTIFY_ADMIN_UNIONIDS"))
    recipients: list[str] = []
    seen: set[str] = set()

    def add_userid(userid: str) -> None:
        normalized = userid.strip()
        if normalized and normalized not in seen:
            recipients.append(normalized)
            seen.add(normalized)

    for identifier in identifiers:
        mapped = userid_map.get(identifier.strip().upper())
        if mapped:
            add_userid(mapped)
        elif assume_same_userid:
            add_userid(identifier)
    for userid in direct_userids:
        add_userid(userid)
    if direct_unionids:
        if not token:
            raise DingTalkNotifyError("DingTalk token is required to resolve unionId recipients.")
        for userid in resolve_unionids_to_userids(direct_unionids, token, repo_root):
            add_userid(userid)
    return recipients


def build_task_url(task: dict[str, Any]) -> str:
    base_url = str(task.get("public_base_url") or os.getenv("THEIA_PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if not base_url:
        return ""
    project_id = str(task.get("project_id", "") or "")
    audit_type = str(task.get("audit_type", "") or "")
    return f"{base_url}/theia/?project_id={project_id}&audit_type={audit_type}&view=report"


def build_absolute_url(path_or_url: object, task: dict[str, Any] | None = None) -> str:
    value = str(path_or_url or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    task = task or {}
    base_url = str(task.get("public_base_url") or os.getenv("THEIA_PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if not base_url:
        return value
    if value.startswith("/"):
        return f"{base_url}{value}"
    return f"{base_url}/{value}"


def build_report_download_url(task: dict[str, Any]) -> str:
    result_paths = task.get("result_paths") if isinstance(task.get("result_paths"), dict) else {}
    for key in ("xlsx", "json"):
        url = build_absolute_url(result_paths.get(key), task)
        if url:
            return url
    return ""


def markdown_link(label: str, url: str) -> str:
    safe_url = quote(str(url or "").strip(), safe=":/?&=%#._-~")
    return f"[{label}]({safe_url})" if safe_url else ""


def _short_error(value: object, limit: int = 900) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    return text[:limit] + ("..." if len(text) > limit else "")


def build_launch_channel_label(task: dict[str, Any]) -> str:
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    if source.get("type") == "dingtalk_aitable":
        return "AI评审管理表"
    return "THEIA网页"


def build_markdown_message(task: dict[str, Any]) -> tuple[str, str]:
    status = str(task.get("status", "") or "")
    status_label = {
        "succeeded": "成功",
        "failed": "失败",
        "cancelled": "已取消",
    }.get(status, status or "未知")
    title = f"Theia审查任务{status_label}"
    audit_label = str(task.get("audit_label", "") or task.get("audit_type", "") or "")
    options_label = str(task.get("audit_options_label", "") or "全量审查")
    project_display = str(task.get("project_display") or task.get("project_id") or "").strip()
    created_by_display = str(task.get("created_by_display") or task.get("created_by") or "").strip()
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    review_admin_display = str(source.get("review_admin_display") or "").strip()
    launch_channel_label = build_launch_channel_label(task)
    lines = [
        f"### {title}",
        f"- 任务ID：{task.get('task_id', '')}",
        f"- 项目：{project_display}",
        f"- 审查类型：{audit_label}",
        f"- 审查范围：{options_label}",
        f"- 任务发起方式：{launch_channel_label}",
    ]
    if source.get("type") == "dingtalk_aitable":
        if review_admin_display:
            lines.append(f"- 评审管理员：{review_admin_display}")
        lines.append(f"- 负责人：{created_by_display}")
    else:
        lines.append(f"- 发起人：{created_by_display}")
    lines.extend([
        f"- 开始时间：{task.get('started_at', '')}",
        f"- 结束时间：{task.get('finished_at', '')}",
        f"- 状态说明：{task.get('message', '')}",
    ])
    if status == "failed":
        error_text = _short_error(task.get("error", ""))
        if error_text:
            lines.extend(["", "**失败摘要：**", error_text])
    task_url = build_task_url(task)
    if task_url:
        lines.extend(["", f"- 报告页面：{markdown_link('打开', task_url)}"])
    download_url = build_report_download_url(task)
    if download_url:
        lines.append(f"- 报告文件：{markdown_link('下载', download_url)}")
    return title, "\n".join(lines)


def send_work_notice(token: str, agent_id: str, userids: list[str], title: str, markdown_text: str) -> dict[str, Any]:
    if not userids:
        return {"sent": False, "reason": "no_recipients"}
    if not agent_id.strip().isdigit():
        raise DingTalkNotifyError("DINGTALK_AGENT_ID must be the numeric DingTalk internal-app agentId.")
    parsed_agent_id = int(agent_id)
    payload = request_oapi_json(
        "POST",
        "/topapi/message/corpconversation/asyncsend_v2",
        token,
        body={
            "agent_id": parsed_agent_id,
            "userid_list": ",".join(userids),
            "msg": {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": markdown_text,
                },
            },
        },
    )
    return {"sent": True, "recipients": userids, "response": payload}


def send_robot_oto_message(token: str, robot_code: str, userids: list[str], title: str, markdown_text: str) -> dict[str, Any]:
    if not userids:
        return {"sent": False, "reason": "no_recipients"}
    if not robot_code.strip():
        raise DingTalkNotifyError("Missing DINGTALK_ROBOT_CODE for robot_oto notification channel.")
    payload = request_json(
        "POST",
        "/v1.0/robot/oToMessages/batchSend",
        token=token,
        body={
            "robotCode": robot_code.strip(),
            "userIds": userids,
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps(
                {
                    "title": title,
                    "text": markdown_text,
                },
                ensure_ascii=False,
            ),
        },
    )
    return {"sent": True, "channel": "robot_oto", "recipients": userids, "response": payload}


def send_task_status_notice(
    task: dict[str, Any],
    repo_root: str | Path,
    admin_ids: list[str] | set[str] | tuple[str, ...] | None = None,
    admin_unionids: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    load_dotenv(root)
    if not _truthy_env("DINGTALK_NOTIFY_ENABLED"):
        return {"enabled": False, "sent": False, "reason": "DINGTALK_NOTIFY_ENABLED is not set"}
    if task.get("status") not in {"succeeded", "failed"}:
        return {"enabled": True, "sent": False, "reason": f"status {task.get('status')} does not require notification"}

    channel = os.getenv("DINGTALK_NOTIFY_CHANNEL", "work_notice").strip().lower()
    token = resolve_access_token_from_env()
    recipients = resolve_recipient_userids(task, admin_ids, root, admin_unionids, token)
    if not recipients:
        return {"enabled": True, "sent": False, "reason": "no recipients resolved"}
    title, markdown_text = build_markdown_message(task)
    if channel in {"robot_oto", "robot", "oto"}:
        result = send_robot_oto_message(token, os.getenv("DINGTALK_ROBOT_CODE", ""), recipients, title, markdown_text)
    elif channel in {"work_notice", "corpconversation", "work"}:
        agent_id = os.getenv("DINGTALK_AGENT_ID", "").strip()
        if not agent_id:
            raise DingTalkNotifyError("Missing DINGTALK_AGENT_ID.")
        result = send_work_notice(token, agent_id, recipients, title, markdown_text)
        result["channel"] = "work_notice"
    else:
        raise DingTalkNotifyError(f"Unsupported DINGTALK_NOTIFY_CHANNEL: {channel}")
    result.update({"enabled": True, "title": title, "channel": result.get("channel", channel)})
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a DingTalk work notice for a Theia audit task.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--task-json", help="Path to a task JSON file.")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--project-display", default="")
    parser.add_argument("--public-base-url", default="")
    parser.add_argument("--audit-type", default="")
    parser.add_argument("--audit-label", default="")
    parser.add_argument("--audit-options-label", default="")
    parser.add_argument("--status", choices=["succeeded", "failed", "cancelled"], default="succeeded")
    parser.add_argument("--created-by", default="")
    parser.add_argument("--created-by-display", default="")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--finished-at", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--error", default="")
    parser.add_argument("--xlsx-url", default="")
    parser.add_argument("--admin-ids", default="")
    parser.add_argument("--admin-unionids", default="")
    parser.add_argument("--channel", choices=["work_notice", "robot_oto"], default="")
    parser.add_argument("--robot-code", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    load_dotenv(repo_root)
    if args.channel:
        os.environ["DINGTALK_NOTIFY_CHANNEL"] = args.channel
    if args.robot_code:
        os.environ["DINGTALK_ROBOT_CODE"] = args.robot_code
    if args.task_json:
        task = json.loads(Path(args.task_json).read_text(encoding="utf-8"))
    else:
        task = {
            "task_id": args.task_id,
            "project_id": args.project_id,
            "project_display": args.project_display,
            "public_base_url": args.public_base_url,
            "audit_type": args.audit_type,
            "audit_label": args.audit_label,
            "audit_options_label": args.audit_options_label,
            "status": args.status,
            "created_by": args.created_by,
            "created_by_display": args.created_by_display,
            "started_at": args.started_at,
            "finished_at": args.finished_at,
            "message": args.message,
            "error": args.error,
            "result_paths": {"xlsx": args.xlsx_url} if args.xlsx_url else {},
        }
    if args.dry_run:
        title, markdown_text = build_markdown_message(task)
        result = {"title": title, "markdown": markdown_text}
        if _truthy_env("DINGTALK_NOTIFY_ENABLED"):
            token = resolve_access_token_from_env()
            result["resolved_recipients"] = resolve_recipient_userids(
                task,
                _split_csv(args.admin_ids),
                repo_root,
                _split_csv(args.admin_unionids),
                token,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    result = send_task_status_notice(task, repo_root, _split_csv(args.admin_ids), _split_csv(args.admin_unionids))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DingTalkError, DingTalkNotifyError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
