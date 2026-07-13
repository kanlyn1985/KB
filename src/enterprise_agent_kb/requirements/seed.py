from __future__ import annotations

import json
from pathlib import Path

from .repository import RequirementRepository, utc_now


def seed_sample_data(root: Path) -> dict[str, int]:
    repo = RequirementRepository(root)
    repo.initialize_schema()
    now = utc_now()

    counts: dict[str, int] = {}
    counts["customers"] = repo.insert_many(
        "customers",
        [
            {
                "customer_id": "CUST-A",
                "customer_name": "客户A",
                "customer_code": "CUST-A",
                "region": "CN",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    counts["customer_projects"] = repo.insert_many(
        "customer_projects",
        [
            {
                "project_id": "CUST-A-P1",
                "customer_id": "CUST-A",
                "project_code": "A-DCDC-P1",
                "project_name": "客户A DCDC P1",
                "product_family": "DCDC",
                "product_variant_id": "DCDC-3KW-72V-A",
                "platform_id": "CUST-A-PLATFORM-1",
                "lifecycle_status": "development",
                "sop_date": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "project_id": "CUST-A-P2",
                "customer_id": "CUST-A",
                "project_code": "A-DCDC-P2",
                "project_name": "客户A DCDC P2",
                "product_family": "DCDC",
                "product_variant_id": "DCDC-3KW-72V-B",
                "platform_id": "CUST-A-PLATFORM-1",
                "lifecycle_status": "development",
                "sop_date": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    counts["requirement_atoms"] = repo.insert_many(
        "requirement_atoms",
        [
            {
                "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE",
                "domain": "DCDC",
                "category": "electrical_performance",
                "canonical_name": "DCDC 输出纹波限制",
                "description": "DCDC 输出电压纹波上限。",
                "parameter_name": "output_ripple",
                "default_unit": "mV",
                "constraint_kind": "max_limit",
                "created_at": now,
                "updated_at": now,
            },
            {
                "atom_id": "REQATOM-DCDC-EFFICIENCY",
                "domain": "DCDC",
                "category": "electrical_performance",
                "canonical_name": "DCDC 效率下限",
                "description": "DCDC 满载或指定工况下效率下限。",
                "parameter_name": "efficiency",
                "default_unit": "%",
                "constraint_kind": "min_limit",
                "created_at": now,
                "updated_at": now,
            },
            {
                "atom_id": "REQATOM-DCDC-SLEEP-CURRENT",
                "domain": "DCDC",
                "category": "low_power",
                "canonical_name": "DCDC 休眠电流限制",
                "description": "DCDC 休眠模式电流上限。",
                "parameter_name": "sleep_current",
                "default_unit": "mA",
                "constraint_kind": "max_limit",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    counts["requirement_profiles"] = repo.insert_many(
        "requirement_profiles",
        [
            {
                "profile_id": "PROFILE-STD-DCDC-MANDATORY",
                "profile_type": "standard_mandatory",
                "owner_type": "standard",
                "owner_id": "STD-DCDC",
                "name": "DCDC 强制标准基线",
                "version": "v1",
                "description": "MVP sample mandatory standard profile.",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "profile_id": "PROFILE-DCDC-BASELINE",
                "profile_type": "product_family_baseline",
                "owner_type": "product_family",
                "owner_id": "DCDC",
                "name": "DCDC 产品族基线需求",
                "version": "v1",
                "description": "MVP sample DCDC baseline profile.",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "profile_id": "PROFILE-CUST-A-DCDC-COMMON",
                "profile_type": "customer_common",
                "owner_type": "customer",
                "owner_id": "CUST-A",
                "name": "客户A DCDC 通用需求画像",
                "version": "v1",
                "description": "MVP sample customer common profile.",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "profile_id": "PROFILE-CUST-A-P1",
                "profile_type": "project_overlay",
                "owner_type": "project",
                "owner_id": "CUST-A-P1",
                "name": "客户A P1 项目覆盖需求",
                "version": "v1",
                "description": "MVP sample P1 overlay.",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "profile_id": "PROFILE-CUST-A-P2",
                "profile_type": "project_overlay",
                "owner_type": "project",
                "owner_id": "CUST-A-P2",
                "name": "客户A P2 项目覆盖需求",
                "version": "v1",
                "description": "MVP sample P2 overlay.",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    inheritance_rows = []
    for child in ["PROFILE-CUST-A-P1", "PROFILE-CUST-A-P2"]:
        inheritance_rows.extend(
            [
                {"child_profile_id": child, "parent_profile_id": "PROFILE-CUST-A-DCDC-COMMON", "priority": 300, "inheritance_type": "normal", "status": "active", "created_at": now},
                {"child_profile_id": child, "parent_profile_id": "PROFILE-DCDC-BASELINE", "priority": 200, "inheritance_type": "normal", "status": "active", "created_at": now},
                {"child_profile_id": child, "parent_profile_id": "PROFILE-STD-DCDC-MANDATORY", "priority": 100, "inheritance_type": "normal", "status": "active", "created_at": now},
            ]
        )
    counts["requirement_profile_inheritance"] = repo.insert_many("requirement_profile_inheritance", inheritance_rows)

    def cond(**kwargs: object) -> str:
        return json.dumps(kwargs, ensure_ascii=False, sort_keys=True)

    counts["requirement_variants"] = repo.insert_many(
        "requirement_variants",
        [
            # Mandatory standard baseline.
            {"variant_id": "REQVAR-STD-RIPPLE", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "profile_id": "PROFILE-STD-DCDC-MANDATORY", "requirement_text": "DCDC 输出纹波 ≤ 80mV", "parameter_name": "output_ripple", "operator": "<=", "value_numeric": 80, "value_text": None, "unit": "mV", "condition_json": cond(load="full_load"), "requirement_type": "limit", "mandatory_level": "mandatory", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-STD-RIPPLE", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-BASE-RIPPLE", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "profile_id": "PROFILE-DCDC-BASELINE", "requirement_text": "DCDC 输出纹波 ≤ 50mV", "parameter_name": "output_ripple", "operator": "<=", "value_numeric": 50, "value_text": None, "unit": "mV", "condition_json": cond(load="full_load"), "requirement_type": "limit", "mandatory_level": "internal_baseline", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-BASE-RIPPLE", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-CUST-A-RIPPLE", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "profile_id": "PROFILE-CUST-A-DCDC-COMMON", "requirement_text": "客户A DCDC 输出纹波 ≤ 30mV", "parameter_name": "output_ripple", "operator": "<=", "value_numeric": 30, "value_text": None, "unit": "mV", "condition_json": cond(load="full_load", temperature="25C"), "requirement_type": "limit", "mandatory_level": "customer_mandatory", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-CUST-A-RIPPLE", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-P1-RIPPLE", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "profile_id": "PROFILE-CUST-A-P1", "requirement_text": "P1 项目 DCDC 输出纹波 ≤ 30mV @ 85℃", "parameter_name": "output_ripple", "operator": "<=", "value_numeric": 30, "value_text": None, "unit": "mV", "condition_json": cond(load="full_load", temperature="85C"), "requirement_type": "limit", "mandatory_level": "project_specific", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-P1-RIPPLE", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-P2-RIPPLE", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "profile_id": "PROFILE-CUST-A-P2", "requirement_text": "P2 项目 DCDC 输出纹波 ≤ 40mV", "parameter_name": "output_ripple", "operator": "<=", "value_numeric": 40, "value_text": None, "unit": "mV", "condition_json": cond(load="full_load", temperature="25C"), "requirement_type": "limit", "mandatory_level": "project_specific", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-P2-RIPPLE", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-BASE-EFF", "atom_id": "REQATOM-DCDC-EFFICIENCY", "profile_id": "PROFILE-DCDC-BASELINE", "requirement_text": "DCDC 满载效率 ≥ 94%", "parameter_name": "efficiency", "operator": ">=", "value_numeric": 94, "value_text": None, "unit": "%", "condition_json": cond(load="full_load"), "requirement_type": "limit", "mandatory_level": "internal_baseline", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-BASE-EFF", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-CUST-A-EFF", "atom_id": "REQATOM-DCDC-EFFICIENCY", "profile_id": "PROFILE-CUST-A-DCDC-COMMON", "requirement_text": "客户A DCDC 满载效率 ≥ 95%", "parameter_name": "efficiency", "operator": ">=", "value_numeric": 95, "value_text": None, "unit": "%", "condition_json": cond(load="full_load"), "requirement_type": "limit", "mandatory_level": "customer_mandatory", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-CUST-A-EFF", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-CUST-A-SLEEP", "atom_id": "REQATOM-DCDC-SLEEP-CURRENT", "profile_id": "PROFILE-CUST-A-DCDC-COMMON", "requirement_text": "客户A DCDC 休眠电流 ≤ 2mA", "parameter_name": "sleep_current", "operator": "<=", "value_numeric": 2, "value_text": None, "unit": "mA", "condition_json": cond(mode="sleep"), "requirement_type": "limit", "mandatory_level": "customer_mandatory", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-CUST-A-SLEEP", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
            {"variant_id": "REQVAR-P1-SLEEP", "atom_id": "REQATOM-DCDC-SLEEP-CURRENT", "profile_id": "PROFILE-CUST-A-P1", "requirement_text": "P1 项目 DCDC 休眠电流 ≤ 1mA", "parameter_name": "sleep_current", "operator": "<=", "value_numeric": 1, "value_text": None, "unit": "mA", "condition_json": cond(mode="sleep"), "requirement_type": "limit", "mandatory_level": "project_specific", "priority": 100, "source_type": "sample", "source_id": None, "evidence_id": "SAMPLE-EV-P1-SLEEP", "fact_id": None, "document_id": None, "status": "active", "created_at": now, "updated_at": now},
        ],
    )
    counts["requirement_overrides"] = repo.insert_many(
        "requirement_overrides",
        [
            {"override_id": "OVR-P1-RIPPLE-CONDITION", "profile_id": "PROFILE-CUST-A-P1", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "base_variant_id": "REQVAR-CUST-A-RIPPLE", "new_variant_id": "REQVAR-P1-RIPPLE", "override_type": "clarify", "reason": "P1 adds high-temperature condition.", "evidence_id": "SAMPLE-EV-P1-RIPPLE", "approval_status": "approved", "approver": "sample", "approved_at": now, "risk_level": "low", "conflict_status": "none", "created_at": now, "updated_at": now},
            {"override_id": "OVR-P2-RIPPLE-LOOSEN", "profile_id": "PROFILE-CUST-A-P2", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "base_variant_id": "REQVAR-CUST-A-RIPPLE", "new_variant_id": "REQVAR-P2-RIPPLE", "override_type": "loosen", "reason": "P2 sample deliberately loosens customer common requirement.", "evidence_id": "SAMPLE-EV-P2-RIPPLE", "approval_status": "draft", "approver": None, "approved_at": None, "risk_level": "medium", "conflict_status": "unchecked", "created_at": now, "updated_at": now},
        ],
    )

    counts["requirement_test_methods"] = repo.insert_many(
        "requirement_test_methods",
        [
            {"test_method_id": "TM-DCDC-RIPPLE", "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE", "name": "DCDC 输出纹波测试", "description": "Measure DCDC output ripple under effective project conditions.", "procedure_json": cond(measure="output_ripple", equipment="oscilloscope"), "evidence_id": "SAMPLE-EV-TM-RIPPLE", "status": "active", "created_at": now, "updated_at": now},
            {"test_method_id": "TM-DCDC-EFFICIENCY", "atom_id": "REQATOM-DCDC-EFFICIENCY", "name": "DCDC 效率测试", "description": "Measure DCDC efficiency at full load.", "procedure_json": cond(measure="efficiency", load="full_load"), "evidence_id": "SAMPLE-EV-TM-EFF", "status": "active", "created_at": now, "updated_at": now},
            {"test_method_id": "TM-DCDC-SLEEP-CURRENT", "atom_id": "REQATOM-DCDC-SLEEP-CURRENT", "name": "DCDC 休眠电流测试", "description": "Measure DCDC sleep current.", "procedure_json": cond(measure="sleep_current", mode="sleep"), "evidence_id": "SAMPLE-EV-TM-SLEEP", "status": "active", "created_at": now, "updated_at": now},
        ],
    )
    counts["requirement_test_cases"] = repo.insert_many(
        "requirement_test_cases",
        [
            {"test_case_id": "TC-DCDC-RIPPLE-FULL-LOAD", "test_method_id": "TM-DCDC-RIPPLE", "project_id": None, "name": "Full-load ripple test", "condition_json": cond(load="full_load"), "priority": 100, "status": "active", "created_at": now, "updated_at": now},
            {"test_case_id": "TC-DCDC-EFF-FULL-LOAD", "test_method_id": "TM-DCDC-EFFICIENCY", "project_id": None, "name": "Full-load efficiency test", "condition_json": cond(load="full_load"), "priority": 100, "status": "active", "created_at": now, "updated_at": now},
            {"test_case_id": "TC-DCDC-SLEEP-CURRENT", "test_method_id": "TM-DCDC-SLEEP-CURRENT", "project_id": None, "name": "Sleep current test", "condition_json": cond(mode="sleep"), "priority": 100, "status": "active", "created_at": now, "updated_at": now},
        ],
    )
    counts["requirement_test_results"] = repo.insert_many(
        "requirement_test_results",
        [
            {"result_id": "TR-P1-RIPPLE-001", "test_case_id": "TC-DCDC-RIPPLE-FULL-LOAD", "project_id": "CUST-A-P1", "measured_value_numeric": 28.0, "measured_value_text": None, "unit": "mV", "status": "recorded", "evidence_id": "SAMPLE-EV-TR-P1-RIPPLE", "executed_at": now, "created_at": now, "updated_at": now},
            {"result_id": "TR-P1-EFF-001", "test_case_id": "TC-DCDC-EFF-FULL-LOAD", "project_id": "CUST-A-P1", "measured_value_numeric": 95.1, "measured_value_text": None, "unit": "%", "status": "recorded", "evidence_id": "SAMPLE-EV-TR-P1-EFF", "executed_at": now, "created_at": now, "updated_at": now},
            {"result_id": "TR-P1-SLEEP-001", "test_case_id": "TC-DCDC-SLEEP-CURRENT", "project_id": "CUST-A-P1", "measured_value_numeric": 0.8, "measured_value_text": None, "unit": "mA", "status": "recorded", "evidence_id": "SAMPLE-EV-TR-P1-SLEEP", "executed_at": now, "created_at": now, "updated_at": now},
            {"result_id": "TR-P2-RIPPLE-001", "test_case_id": "TC-DCDC-RIPPLE-FULL-LOAD", "project_id": "CUST-A-P2", "measured_value_numeric": 45.0, "measured_value_text": None, "unit": "mV", "status": "recorded", "evidence_id": "SAMPLE-EV-TR-P2-RIPPLE", "executed_at": now, "created_at": now, "updated_at": now},
        ],
    )

    return counts
