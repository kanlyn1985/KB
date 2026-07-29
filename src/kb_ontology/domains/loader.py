"""Domain pack loader.

Reads JSON (or tiny YAML subset) files from a domain directory and builds
a DomainPack. File-per-concern convention:

  domain.json       → meta (domain_id, name, version, description)
  classes.json      → ClassSpec definitions
  relations.json    → domain-specific RelationTypeSpec (Core types are injected)
  terminology.json  → canonical entity IDs → aliases

Missing files are tolerated (empty defaults). Only domain.json (or .yaml)
is required — without it, loading fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_ontology.domains.schema import (
    AttributeSpec,
    ClassSpec,
    DomainPack,
    DomainPackError,
    RelationRole,
    RelationTypeSpec,
)


def load_domain_pack(domain_dir: Path) -> DomainPack:
    """Load a domain pack from a directory of JSON/YAML files."""
    domain_dir = Path(domain_dir)
    if not domain_dir.is_dir():
        raise DomainPackError(f"domain directory not found: {domain_dir}")

    meta = _load_mapping(domain_dir / "domain.json", domain_dir / "domain.yaml")
    if not meta:
        raise DomainPackError(f"missing domain metadata in {domain_dir}")

    domain_id = str(meta.get("domain_id") or meta.get("id") or "").strip()
    if not domain_id:
        raise DomainPackError(f"domain_id is required in {domain_dir}")

    classes_raw = _load_mapping(domain_dir / "classes.json", domain_dir / "classes.yaml")
    relations_raw = _load_mapping(domain_dir / "relations.json", domain_dir / "relations.yaml")
    terminology_raw = _load_mapping(domain_dir / "terminology.json", domain_dir / "terminology.yaml")

    return DomainPack(
        domain_id=domain_id,
        name=str(meta.get("name") or domain_id),
        version=str(meta.get("version") or "0.1.0"),
        description=str(meta.get("description") or ""),
        classes=_load_classes(classes_raw),
        relation_types=_load_relation_types(relations_raw),
        terminology=_load_terminology(terminology_raw),
    )


# ── File-level loader ──


def _load_mapping(json_path: Path, yaml_path: Path | None = None) -> dict[str, Any]:
    """Load JSON or tiny YAML. Returns empty dict if file doesn't exist."""
    if json_path.exists():
        text = json_path.read_text(encoding="utf-8")
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise DomainPackError(f"{json_path} must contain a JSON object")
        return payload
    if yaml_path and yaml_path.exists():
        return _parse_tiny_yaml(yaml_path.read_text(encoding="utf-8"))
    return {}


# ── Section parsers ──


def _load_classes(raw: dict[str, Any]) -> dict[str, ClassSpec]:
    payload = raw.get("classes", raw)
    if not isinstance(payload, dict):
        return {}
    result: dict[str, ClassSpec] = {}
    for name, spec in payload.items():
        if not isinstance(spec, dict):
            spec = {}
        result[str(name)] = _build_class_spec(str(name), spec)
    return result


def _build_class_spec(name: str, spec: dict[str, Any]) -> ClassSpec:
    attribute_template = _build_attribute_template(spec.get("attributes") or spec.get("attribute_template") or {})
    relation_roles = _build_relation_roles(spec.get("relation_roles") or [])
    identity_attrs_raw = spec.get("identity_attributes") or []
    if isinstance(identity_attrs_raw, str):
        identity_attrs_raw = [a.strip() for a in identity_attrs_raw.split(",") if a.strip()]
    display_secondary = spec.get("display_secondary") or []
    if isinstance(display_secondary, str):
        display_secondary = [s.strip() for s in display_secondary.split(",") if s.strip()]

    return ClassSpec(
        name=name,
        description=str(spec.get("description") or ""),
        attribute_template=attribute_template,
        relation_roles=relation_roles,
        identity_attributes=[str(a) for a in identity_attrs_raw if str(a).strip()],
        identity_rule=str(spec.get("identity_rule") or ""),
        display_primary=str(spec.get("display_primary") or "name"),
        display_secondary=[str(s) for s in display_secondary if str(s).strip()],
    )


def _build_attribute_template(raw: dict[str, Any]) -> dict[str, AttributeSpec]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, AttributeSpec] = {}
    for attr_name, attr_spec in raw.items():
        if not isinstance(attr_spec, dict):
            attr_spec = {"value_type": "string", "required": False}
        value_type = str(attr_spec.get("value_type") or attr_spec.get("type") or "string")
        required_raw = attr_spec.get("required")
        required = required_raw in (True, "true", "True", "yes", 1)
        enum_values = attr_spec.get("enum_values") or attr_spec.get("enum") or []
        if not isinstance(enum_values, list):
            enum_values = []
        result[str(attr_name)] = AttributeSpec(
            name=str(attr_name),
            value_type=value_type,
            required=required,
            description=str(attr_spec.get("description") or ""),
            enum_values=[str(v) for v in enum_values if str(v).strip()],
        )
    return result


def _build_relation_roles(raw: list[Any]) -> list[RelationRole]:
    if not isinstance(raw, list):
        return []
    result: list[RelationRole] = []
    for item in raw:
        if isinstance(item, dict):
            rel_type = str(item.get("relation_type") or item.get("type") or "")
            targets = item.get("target_classes") or []
            if not isinstance(targets, list):
                targets = []
            if rel_type:
                result.append(
                    RelationRole(
                        relation_type=rel_type,
                        target_classes=[str(t) for t in targets if str(t).strip()],
                    )
                )
        elif isinstance(item, str):
            result.append(RelationRole(relation_type=item))
    return result


def _load_relation_types(raw: dict[str, Any]) -> dict[str, RelationTypeSpec]:
    payload = raw.get("relation_types", raw)
    if not isinstance(payload, dict):
        return {}
    result: dict[str, RelationTypeSpec] = {}
    for name, spec in payload.items():
        if not isinstance(spec, dict):
            spec = {}
        result[str(name)] = RelationTypeSpec(
            name=str(name),
            description=str(spec.get("description") or ""),
            inverse_name=str(spec.get("inverse_name")) if spec.get("inverse_name") else None,
            is_core=False,
        )
    return result


def _load_terminology(raw: dict[str, Any]) -> dict[str, list[str]]:
    payload = raw.get("terms", raw)
    if not isinstance(payload, dict):
        return {}
    result: dict[str, list[str]] = {}
    for canonical, spec in payload.items():
        if isinstance(spec, dict):
            aliases = spec.get("aliases", [])
        elif isinstance(spec, list):
            aliases = spec
        else:
            aliases = [str(spec)]
        result[str(canonical)] = [str(a) for a in aliases if str(a).strip()]
    return result


# ── Tiny YAML subset parser (copied from agent_kb_core, deliberately minimal) ──


def _parse_tiny_yaml(text: str) -> dict[str, Any]:
    """Parse a constrained YAML-like format.

    Supports top-level scalars, nested dicts, and lists of scalars.
    Not a general YAML parser — production can switch to PyYAML.
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
