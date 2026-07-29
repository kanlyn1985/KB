"""Schema prompt builder — renders DomainPack into LLM-readable text.

Serializes the Class/Relation/Attribute definitions from a DomainPack into
a structured text block that the LLM can read and follow during extraction.
"""

from __future__ import annotations

from kb_ontology.domains.schema import DomainPack


def build_schema_description(domain_pack: DomainPack) -> str:
    """Build a human/LLM-readable description of the ontology schema.

    Lists all classes, their attribute templates, relation roles, and
    identity rules. This text is injected into the extraction prompt.
    """
    lines: list[str] = []
    lines.append(f"领域: {domain_pack.domain_id}")
    lines.append(f"领域名称: {domain_pack.name}")
    lines.append("")
    lines.append("可用的 Class 及其结构:")
    lines.append("")

    for class_name, cls_spec in domain_pack.classes.items():
        lines.append(f"### {class_name}")
        if cls_spec.description:
            lines.append(f"  说明: {cls_spec.description}")
        lines.append("")

        # Attribute template
        if cls_spec.attribute_template:
            lines.append("  属性模板:")
            for attr_name, attr_spec in cls_spec.attribute_template.items():
                required_tag = "必填" if attr_spec.required else "选填"
                type_desc = attr_spec.value_type
                if attr_spec.enum_values:
                    type_desc += f" (枚举: {'/'.join(attr_spec.enum_values)})"
                desc = f" — {attr_spec.description}" if attr_spec.description else ""
                lines.append(f"    - {attr_name}: {type_desc}, {required_tag}{desc}")
            lines.append("")
        else:
            lines.append("  属性模板: (无)")
            lines.append("")

        # Relation roles
        if cls_spec.relation_roles:
            lines.append("  关系角色 (该 Class 的实体可作为以下关系的 source):")
            for role in cls_spec.relation_roles:
                targets = ", ".join(role.target_classes) if role.target_classes else "(任意)"
                lines.append(f"    - {role.relation_type} → {targets}")
            lines.append("")

        # Identity rule
        if cls_spec.identity_attributes:
            identity = " + ".join(cls_spec.identity_attributes)
            lines.append(f"  唯一性键: {identity}")
        if cls_spec.identity_rule:
            lines.append(f"  唯一性规则: {cls_spec.identity_rule}")
        lines.append("")

    # Core + domain relation types
    lines.append("### 关系类型说明")
    lines.append("Core 通用关系 (所有领域可用):")
    for rt_name, rt_spec in domain_pack.all_relation_types.items():
        if rt_spec.is_core:
            inverse = f" (逆关系: {rt_spec.inverse_name})" if rt_spec.inverse_name else ""
            lines.append(f"  - {rt_name}: {rt_spec.description}{inverse}")
    lines.append("")
    domain_rels = {
        k: v for k, v in domain_pack.all_relation_types.items() if not v.is_core
    }
    if domain_rels:
        lines.append("领域特有关系:")
        for rt_name, rt_spec in domain_rels.items():
            inverse = f" (逆关系: {rt_spec.inverse_name})" if rt_spec.inverse_name else ""
            lines.append(f"  - {rt_name}: {rt_spec.description}{inverse}")
        lines.append("")

    return "\n".join(lines)
