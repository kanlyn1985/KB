"""Build a hand-curated OBC ontology from real standard codes.

This script populates the new ontology system (``src/kb1_ontology/``)
with a representative slice of the OBC systems-engineering
knowledge base. It demonstrates that the Phase 0-4 modules can
together represent real-world knowledge.

Run:
    python scripts/ontology_demo/build_obc_ontology.py

After it runs, the demo query script can be used to traverse
the resulting graph.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ensure src/ is on the import path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.attribute_store import (
    VALUE_TYPE_NUMBER,
    VALUE_TYPE_RANGE,
    VALUE_TYPE_REFERENCE,
    VALUE_TYPE_STRING,
    set_attribute,
)
from kb1_ontology.attribute_store.schema import (
    ensure_schema as ensure_attribute_schema,
)
from kb1_ontology.class_registry import (
    ensure_schema as ensure_class_schema,
    seed_core_classes,
)
from kb1_ontology.db import connect, default_db_path
from kb1_ontology.entity_manager import (
    ensure_schema as ensure_entity_schema,
    find_or_create_entity,
)
from kb1_ontology.entity_manager.schema import (
    ensure_schema as ensure_entity_schema_module,
)
from kb1_ontology.relation_registry import (
    CATEGORY_REFERENTIAL,
    CATEGORY_STRUCTURAL,
    create_relation,
    create_relation_def,
    ensure_schema as ensure_relation_schema,
)
from kb1_ontology.relation_registry.schema import (
    ensure_schema as ensure_relation_schema_module,
)


# Workspace path (where the ontology.db will live)
WORKSPACE = ROOT / "knowledge_base"


# A small, hand-curated slice of the OBC knowledge base.
# This is not auto-discovered; it is the "core seed" the way
# domain experts would hand-author it.
STANDARDS = [
    # (raw_name, class_id, title, role)
    ("ISO 14229-1",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 1: Application layer",
     "diagnostic_protocol"),
    ("ISO 14229-2",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 2: Session layer services",
     "diagnostic_protocol"),
    ("ISO 14229-3",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 3: UDS on CAN",
     "diagnostic_protocol"),
    ("ISO 14229-4",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 4: UDS on FlexRay",
     "diagnostic_protocol"),
    ("ISO 14229-5",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 5: UDS on IP",
     "diagnostic_protocol"),
    ("ISO 14229-6",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 6: UDS on K-Line",
     "diagnostic_protocol"),
    ("ISO 14229-7",   "CLS-OBC-STANDARD", "Road vehicles — UDS — Part 7: UDS on LIN",
     "diagnostic_protocol"),
    ("GB/T 18487.1",  "CLS-OBC-STANDARD", "Conductive charging system for EVs — General requirements",
     "charging_spec"),
    ("GB/T 18487.4",  "CLS-OBC-STANDARD", "V2L (Vehicle-to-Load) requirements",
     "charging_spec"),
    ("GB/T 18487.5",  "CLS-OBC-STANDARD", "DC charging system for EVs",
     "charging_spec"),
    ("GB/T 20234.2",  "CLS-OBC-STANDARD", "AC charging coupler",
     "charging_spec"),
    ("QC/T 1036",     "CLS-OBC-STANDARD", "Power inverter for EVs (QC/T automotive standard)",
     "product_spec"),
    ("ISO 15118",     "CLS-OBC-STANDARD", "Vehicle-to-Grid Communication Interface",
     "charging_protocol"),
    # Additional standards from legacy DB
    ("GB/T 40432",    "CLS-OBC-STANDARD", "Electric vehicle conductive charging system — Communication protocol between off-board conductive charger and battery management system",
     "charging_protocol"),
    ("IEC 61851-1",   "CLS-OBC-STANDARD", "Electric vehicle conductive charging system — Part 1: General requirements",
     "charging_spec"),
    ("AutomotiveSPICE", "CLS-OBC-STANDARD", "Automotive SPICE Process Assessment Model",
     "process_standard"),
    ("V2G",           "CLS-OBC-STANDARD", "Vehicle-to-Grid communication requirements",
     "charging_protocol"),
    ("CCU",           "CLS-OBC-STANDARD", "On-Board Charger Unit software functional requirements",
     "product_spec"),
]

# Each tuple: (referencer_name, referencee_name, rationale)
REFERENCE_EDGES = [
    # 14229-7 → references → 14229-1, 14229-2, 14229-3
    ("ISO 14229-7", "ISO 14229-1", "UDSonLIN uses UDSonCAN's session layer"),
    ("ISO 14229-7", "ISO 14229-2", "UDSonLIN implements session layer services"),
    ("ISO 14229-7", "ISO 14229-3", "UDSonLIN reuses CAN framing concepts"),
    # 14229-3 → references → 14229-1, 14229-2
    ("ISO 14229-3", "ISO 14229-1", "UDSonCAN implements application layer"),
    ("ISO 14229-3", "ISO 14229-2", "UDSonCAN implements session layer"),
    # 14229-4 → 14229-1
    ("ISO 14229-4", "ISO 14229-1", "UDSonFlexRay implements application layer"),
    # 14229-5 → 14229-1, 14229-2
    ("ISO 14229-5", "ISO 14229-1", "UDSonIP implements application layer"),
    ("ISO 14229-5", "ISO 14229-2", "UDSonIP implements session layer"),
    # 14229-6 → 14229-1
    ("ISO 14229-6", "ISO 14229-1", "UDSonK-Line implements application layer"),
    # Charging standards cross-reference each other
    ("GB/T 18487.1", "GB/T 18487.4", "General spec references V2L requirements"),
    ("GB/T 18487.1", "GB/T 18487.5", "General spec references DC charging"),
    ("GB/T 18487.4", "GB/T 20234.2", "V2L uses AC coupler"),
    # ISO 15118 (V2G) is referenced by charging standards
    ("GB/T 18487.1", "ISO 15118", "General charging spec references V2G protocol"),
    # Additional references for new standards
    ("IEC 61851-1", "GB/T 18487.1", "IEC general requirements referenced by GB/T"),
    ("GB/T 40432", "GB/T 18487.1", "Communication protocol references charging general spec"),
    ("V2G", "ISO 15118", "V2G requirements reference V2G communication protocol"),
    ("CCU", "QC/T 1036", "CCU software requirements reference power inverter spec"),
    ("AutomotiveSPICE", "CCU", "Process assessment model applies to CCU development"),
]


# Each tuple: (entity_name, attribute_name, value_text, value_type)
ATTRIBUTES = [
    # ISO 14229-3 UDS on CAN timing parameters
    ("ISO 14229-3", "P2_Server_Timing", "50 ms", VALUE_TYPE_NUMBER),
    ("ISO 14229-3", "P2_Star_Server_Timing", "5000 ms", VALUE_TYPE_NUMBER),
    ("ISO 14229-3", "S3_Server_Timing", "5000 ± 100 ms", VALUE_TYPE_RANGE),
    ("ISO 14229-3", "title", "Road vehicles — UDS on CAN", VALUE_TYPE_STRING),
    # ISO 14229-1 application layer
    ("ISO 14229-1", "title", "Road vehicles — UDS — Application layer", VALUE_TYPE_STRING),
    ("ISO 14229-1", "service_DiagnosticSessionControl", "0x10", VALUE_TYPE_STRING),
    ("ISO 14229-1", "service_ECUReset", "0x11", VALUE_TYPE_STRING),
    ("ISO 14229-1", "service_ReadDataByIdentifier", "0x22", VALUE_TYPE_STRING),
    ("ISO 14229-1", "service_SecurityAccess", "0x27", VALUE_TYPE_STRING),
    ("ISO 14229-1", "service_TesterPresent", "0x3E", VALUE_TYPE_STRING),
    # ISO 14229-2 session layer
    ("ISO 14229-2", "title", "Road vehicles — UDS — Session layer services", VALUE_TYPE_STRING),
    ("ISO 14229-2", "service_DiagnosticSessionControl", "0x10", VALUE_TYPE_STRING),
    ("ISO 14229-2", "service_TesterPresent", "0x3E", VALUE_TYPE_STRING),
    # ISO 14229-3 UDS on CAN
    ("ISO 14229-3", "service_DiagnosticSessionControl", "0x10", VALUE_TYPE_STRING),
    ("ISO 14229-3", "service_ECUReset", "0x11", VALUE_TYPE_STRING),
    # ISO 14229-7 UDS on LIN
    ("ISO 14229-7", "title", "Road vehicles — UDS on LIN", VALUE_TYPE_STRING),
    ("ISO 14229-7", "P2_Server_Timing", "50 ms", VALUE_TYPE_NUMBER),
    ("ISO 14229-7", "service_DiagnosticSessionControl", "0x10", VALUE_TYPE_STRING),
    ("ISO 14229-7", "service_CommunicationControl", "0x28", VALUE_TYPE_STRING),
    # ISO 15118
    ("ISO 15118", "title", "Vehicle-to-Grid Communication Interface", VALUE_TYPE_STRING),
    # QC/T 1036
    ("QC/T 1036", "title", "Power inverter for EVs (QC/T automotive standard)", VALUE_TYPE_STRING),
    # GB/T 18487.1 general charging
    ("GB/T 18487.1", "title", "Conductive charging system for EVs", VALUE_TYPE_STRING),
    ("GB/T 18487.1", "rated_voltage_AC", "250 V", VALUE_TYPE_NUMBER),
    ("GB/T 18487.1", "rated_current_AC", "16 A", VALUE_TYPE_NUMBER),
    # GB/T 18487.4 V2L
    ("GB/T 18487.4", "title", "V2L (Vehicle-to-Load) requirements", VALUE_TYPE_STRING),
    ("GB/T 18487.4", "max_output_voltage", "250 V", VALUE_TYPE_NUMBER),
    ("GB/T 18487.4", "max_output_frequency", "50 Hz", VALUE_TYPE_NUMBER),
    # Additional standards
    ("GB/T 40432", "title", "EV conductive charging — Communication protocol between off-board charger and BMS", VALUE_TYPE_STRING),
    ("IEC 61851-1", "title", "EV conductive charging system — Part 1: General requirements", VALUE_TYPE_STRING),
    ("AutomotiveSPICE", "title", "Automotive SPICE Process Assessment Model", VALUE_TYPE_STRING),
    ("V2G", "title", "Vehicle-to-Grid communication requirements", VALUE_TYPE_STRING),
    ("CCU", "title", "On-Board Charger Unit software functional requirements", VALUE_TYPE_STRING),
]


def build() -> None:
    db_path = default_db_path(WORKSPACE)
    print(f"Building ontology at: {db_path}")
    print()

    conn = connect(db_path)
    try:
        # 1. Install all schemas
        ensure_class_schema(conn)
        ensure_entity_schema_module(conn)
        ensure_relation_schema_module(conn)
        ensure_attribute_schema(conn)
        # 2. Seed core classes
        n_classes = seed_core_classes(conn)
        print(f"Seeded {n_classes} core classes (Meta + OBC Domain)")
        # 3. Register core relations
        # Seed: structural / attributive / referential / temporal
        for rel_name, cat in [
            ("is-a", CATEGORY_STRUCTURAL),
            ("part-of", CATEGORY_STRUCTURAL),
            ("has-attribute", "attributive"),
            ("references", CATEGORY_REFERENTIAL),
        ]:
            if conn.execute(
                "SELECT 1 FROM relation_def WHERE relation_name = ?",
                (rel_name,),
            ).fetchone() is None:
                create_relation_def(
                    conn, rel_name, cat,
                    inverse_name=f"{rel_name}-inv",
                )
        # 4. Create standard entities
        print()
        print("Creating standard entities:")
        entity_ids: dict[str, str] = {}
        for raw_name, class_id, title, role in STANDARDS:
            e, created = find_or_create_entity(
                conn, raw_name, class_id=class_id, domain="OBC",
                description=title, source_path=f"docs/standards/{raw_name}",
            )
            entity_ids[raw_name] = e.entity_id
            marker = "✓" if created else "·"
            print(f"  {marker} {e.entity_id}  {raw_name}  ({class_id})")
        # 5. Create reference relations
        print()
        print("Creating reference relations:")
        n_refs = 0
        for src_name, dst_name, _rationale in REFERENCE_EDGES:
            if src_name not in entity_ids or dst_name not in entity_ids:
                continue
            try:
                create_relation(
                    conn, "references", "entity",
                    entity_ids[src_name], "entity",
                    entity_ids[dst_name], domain="OBC",
                )
                n_refs += 1
            except Exception as e:
                print(f"  (skip {src_name}->{dst_name}: {e})")
        print(f"Created {n_refs} reference relations")
        # 6. Set attributes
        print()
        print("Setting attributes:")
        n_attrs = 0
        for entity_name, attr_name, value_text, value_type in ATTRIBUTES:
            if entity_name not in entity_ids:
                continue
            eid = entity_ids[entity_name]
            if value_type == VALUE_TYPE_REFERENCE:
                # Skip — reference-type attributes need an extra
                # value_ref_id argument; not used in this seed.
                continue
            try:
                set_attribute(
                    conn, "entity", eid, attr_name,
                    value_text=value_text, value_type=value_type,
                )
                n_attrs += 1
            except Exception as e:
                print(f"  (skip {entity_name}.{attr_name}: {e})")
        print(f"Set {n_attrs} attributes")
        print()
        print("=" * 50)
        print(f"✅ Ontology built successfully at {db_path}")
        print(f"   - {len(STANDARDS)} standard entities")
        print(f"   - {n_refs} reference relations")
        print(f"   - {n_attrs} typed attributes")
    finally:
        conn.close()


if __name__ == "__main__":
    build()
