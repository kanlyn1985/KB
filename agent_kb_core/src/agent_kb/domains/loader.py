from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import AnswerContractSpec, DomainPack, HiddenContextRule, ObjectTypeSpec, RelationTypeSpec


class DomainPackError(ValueError):
    """Raised when a domain pack is missing required metadata or has invalid shape."""


def _load_mapping(path: Path) -> dict[str, Any]:
    """Load JSON or a small YAML subset.

    MVP-1 keeps dependencies empty. JSON is fully supported. YAML support is a
    minimal key/value/list subset intended for simple domain packs; production
    can later switch to PyYAML.
    """

    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise DomainPackError(f"{path} must contain a JSON object")
        return payload
    return _parse_tiny_yaml(text)


def _parse_tiny_yaml(text: str) -> dict[str, Any]:
    """Parse a constrained YAML-like format used by the bootstrap domain packs.

    This parser is deliberately small and conservative. It supports top-level
    scalars, nested dictionaries, and lists of scalars. It is not a general YAML
    parser.
    """

    result: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, result)]
    last_key_at_indent: dict[int, str] = {}

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            value = _coerce_scalar(line[2:].strip())
            if not isinstance(parent, list):
                raise DomainPackError("list item without list parent")
            parent.append(value)
            continue

        if ":" not in line:
            raise DomainPackError(f"invalid domain pack line: {raw_line}")
        key, value_raw = line.split(":", 1)
        key = key.strip()
        value_raw = value_raw.strip()
        if value_raw == "":
            # Decide list vs dict by looking ahead is intentionally avoided.
            # Default to dict; explicit [] can be used for empty lists.
            value: Any = {}
        else:
            value = _coerce_scalar(value_raw)
        if isinstance(parent, dict):
            parent[key] = value
            last_key_at_indent[indent] = key
        else:
            raise DomainPackError("nested mapping under list is not supported in tiny yaml")
        if isinstance(value, dict):
            stack.append((indent, value))
        elif isinstance(value, list):
            stack.append((indent, value))
    return result


def _coerce_scalar(value: str) -> Any:
    if value in {"[]", ""}:
        return [] if value == "[]" else ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return value.strip('"').strip("'")


def load_domain_pack(domain_dir: Path) -> DomainPack:
    domain_meta = _load_mapping(domain_dir / "domain.json") or _load_mapping(domain_dir / "domain.yaml")
    if not domain_meta:
        raise DomainPackError(f"missing domain metadata in {domain_dir}")
    domain_id = str(domain_meta.get("domain_id") or domain_meta.get("id") or "").strip()
    if not domain_id:
        raise DomainPackError(f"domain_id is required in {domain_dir}")

    object_types_raw = _load_mapping(domain_dir / "object_types.json") or _load_mapping(domain_dir / "object_types.yaml")
    relation_types_raw = _load_mapping(domain_dir / "relation_types.json") or _load_mapping(domain_dir / "relation_types.yaml")
    terminology_raw = _load_mapping(domain_dir / "terminology.json") or _load_mapping(domain_dir / "terminology.yaml")
    answer_contracts_raw = _load_mapping(domain_dir / "answer_contracts.json") or _load_mapping(domain_dir / "answer_contracts.yaml")
    hidden_context_raw = _load_mapping(domain_dir / "hidden_context.json") or _load_mapping(domain_dir / "hidden_context.yaml")

    return DomainPack(
        domain_id=domain_id,
        name=str(domain_meta.get("name") or domain_id),
        version=str(domain_meta.get("version") or "0.1.0"),
        description=str(domain_meta.get("description") or ""),
        object_types=_load_object_types(object_types_raw),
        relation_types=_load_relation_types(relation_types_raw),
        terminology=_load_terminology(terminology_raw),
        answer_contracts=_load_answer_contracts(answer_contracts_raw),
        hidden_context_rules=_load_hidden_context(hidden_context_raw),
    )


def _load_object_types(raw: dict[str, Any]) -> dict[str, ObjectTypeSpec]:
    payload = raw.get("object_types", raw)
    result: dict[str, ObjectTypeSpec] = {}
    if not isinstance(payload, dict):
        return result
    for name, spec in payload.items():
        if isinstance(spec, dict):
            result[str(name)] = ObjectTypeSpec(
                name=str(name),
                description=str(spec.get("description") or ""),
                properties=[str(item) for item in spec.get("properties", []) if str(item).strip()],
            )
        else:
            result[str(name)] = ObjectTypeSpec(name=str(name), description=str(spec or ""))
    return result


def _load_relation_types(raw: dict[str, Any]) -> dict[str, RelationTypeSpec]:
    payload = raw.get("relation_types", raw)
    result: dict[str, RelationTypeSpec] = {}
    if not isinstance(payload, dict):
        return result
    for name, spec in payload.items():
        if not isinstance(spec, dict):
            spec = {}
        result[str(name)] = RelationTypeSpec(
            name=str(name),
            source_types=[str(item) for item in spec.get("source_types", [])],
            target_types=[str(item) for item in spec.get("target_types", [])],
            description=str(spec.get("description") or ""),
        )
    return result


def _load_terminology(raw: dict[str, Any]) -> dict[str, list[str]]:
    payload = raw.get("terms", raw)
    result: dict[str, list[str]] = {}
    if not isinstance(payload, dict):
        return result
    for canonical, spec in payload.items():
        if isinstance(spec, dict):
            aliases = spec.get("aliases", [])
        elif isinstance(spec, list):
            aliases = spec
        else:
            aliases = [str(spec)]
        result[str(canonical)] = [str(item) for item in aliases if str(item).strip()]
    return result


def _load_answer_contracts(raw: dict[str, Any]) -> dict[str, AnswerContractSpec]:
    payload = raw.get("answer_contracts", raw)
    result: dict[str, AnswerContractSpec] = {}
    if not isinstance(payload, dict):
        return result
    for name, spec in payload.items():
        if not isinstance(spec, dict):
            spec = {}
        result[str(name)] = AnswerContractSpec(
            name=str(name),
            intent=str(spec.get("intent") or name),
            required_sections=[str(item) for item in spec.get("required_sections", [])],
            optional_sections=[str(item) for item in spec.get("optional_sections", [])],
            preferred_object_types=[str(item) for item in spec.get("preferred_object_types", [])],
            preferred_fact_types=[str(item) for item in spec.get("preferred_fact_types", [])],
        )
    return result


def _load_hidden_context(raw: dict[str, Any]) -> list[HiddenContextRule]:
    payload = raw.get("hidden_context_rules", [])
    if not isinstance(payload, list):
        return []
    result: list[HiddenContextRule] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        result.append(
            HiddenContextRule(
                rule_id=str(item.get("rule_id") or item.get("id") or ""),
                trigger=dict(item.get("trigger") or {}),
                inject=[str(value) for value in item.get("inject", [])],
            )
        )
    return result
