"""Core class seed for the KB1 ontology system.

This is the hand-curated set of "core" classes — the abstract
Meta-layer universals plus the first engineering-role Domain
(Systems Engineering, focused on OBC). They are loaded by
``seed_core_classes(conn)`` and are idempotent: re-running the
seed does not duplicate rows.

Per the design decision in docs/ontology/CONTEXT.md:
- Core classes are manually defined
- Domain subtrees are organized by engineering role
- New domains can be added later without modifying the Meta layer

Note on naming: the current Domain is named "OBC" for now because
the OBC system is the prototype. The class hierarchy is shared
across all Systems Engineering work — the "OBC" label refers to
the systems engineer's scope, not just one product. The role tag
on documents is separate from the class domain.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .crud import ClassRegistryError, create_class, get_class
from .schema import LAYER_DOMAIN, LAYER_META, ensure_schema


# The current Domain identifier. We keep it short ("OBC") to
# match the prototype product, but its meaning is "Systems
# Engineering" — see CONTEXT.md.
CURRENT_DOMAIN = "OBC"


@dataclass(frozen=True)
class ClassSeed:
    """A single class to seed."""
    class_id: str
    class_name: str
    parent_class_id: str | None
    layer: str
    domain: str | None
    description: str | None


# Meta-layer universals.
# These are the abstract kinds of things the knowledge base
# can talk about. They are not specific to any engineering role.
META_SEEDS: tuple[ClassSeed, ...] = (
    ClassSeed(
        class_id="CLS-META-THING",
        class_name="Thing",
        parent_class_id=None,
        layer=LAYER_META,
        domain=None,
        description="The root of all classes. Every other class is a "
                    "specialization of Thing.",
    ),
    ClassSeed(
        class_id="CLS-META-INFORMATION-ENTITY",
        class_name="InformationEntity",
        parent_class_id="CLS-META-THING",
        layer=LAYER_META,
        domain=None,
        description="Any entity whose primary purpose is to carry "
                    "information: a document, a standard, a definition.",
    ),
    ClassSeed(
        class_id="CLS-META-PHYSICAL-ENTITY",
        class_name="PhysicalEntity",
        parent_class_id="CLS-META-THING",
        layer=LAYER_META,
        domain=None,
        description="A real-world physical object: a device, a "
                    "component, a system.",
    ),
    ClassSeed(
        class_id="CLS-META-PROCESS-ENTITY",
        class_name="ProcessEntity",
        parent_class_id="CLS-META-THING",
        layer=LAYER_META,
        domain=None,
        description="Something that happens over time: a charging "
                    "session, a test procedure, a state transition.",
    ),
    ClassSeed(
        class_id="CLS-META-CONCEPT-ENTITY",
        class_name="ConceptEntity",
        parent_class_id="CLS-META-THING",
        layer=LAYER_META,
        domain=None,
        description="An abstract concept: a parameter, a protocol, "
                    "a constraint. Not a physical object or a process.",
    ),
    ClassSeed(
        class_id="CLS-META-ROLE-ENTITY",
        class_name="RoleEntity",
        parent_class_id="CLS-META-THING",
        layer=LAYER_META,
        domain=None,
        description="A role played by a person or organization: "
                    "an engineer, a tester, a reviewer.",
    ),
)


# Systems Engineering Domain — the first engineering-role subtree.
# The class_ids use the OBC prefix for historical continuity, but
# the classes themselves are what a Systems Engineer needs to
# reason about an OBC system (the system integration perspective
# for On-Board Chargers).
OBC_SEEDS: tuple[ClassSeed, ...] = (
    # InformationEntity sub-tree
    ClassSeed(
        class_id="CLS-OBC-STANDARD",
        class_name="Standard",
        parent_class_id="CLS-META-INFORMATION-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A published standard (ISO, GB/T, IEC, QC/T, ...) "
                    "relevant to systems engineering.",
    ),
    ClassSeed(
        class_id="CLS-OBC-SPECIFICATION",
        class_name="Specification",
        parent_class_id="CLS-META-INFORMATION-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="An internal or vendor-provided specification "
                    "document.",
    ),
    ClassSeed(
        class_id="CLS-OBC-GUIDELINE",
        class_name="Guideline",
        parent_class_id="CLS-META-INFORMATION-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A best-practice or design guideline.",
    ),
    # PhysicalEntity sub-tree
    ClassSeed(
        class_id="CLS-OBC-DEVICE",
        class_name="Device",
        parent_class_id="CLS-META-PHYSICAL-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A device or subsystem (an OBC unit, a charging "
                    "controller, a BMS).",
    ),
    ClassSeed(
        class_id="CLS-OBC-COMPONENT",
        class_name="Component",
        parent_class_id="CLS-META-PHYSICAL-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A discrete hardware component (a connector, a "
                    "power module, a relay).",
    ),
    # ProcessEntity sub-tree
    ClassSeed(
        class_id="CLS-OBC-CHARGING-PROCESS",
        class_name="ChargingProcess",
        parent_class_id="CLS-META-PROCESS-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A charging process: slow charging, fast "
                    "charging, V2L, V2G.",
    ),
    ClassSeed(
        class_id="CLS-OBC-DIAGNOSTIC-PROCESS",
        class_name="DiagnosticProcess",
        parent_class_id="CLS-META-PROCESS-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A diagnostic or handshake process (UDS, "
                    "CommunicationControl).",
    ),
    # ConceptEntity sub-tree
    ClassSeed(
        class_id="CLS-OBC-PARAMETER",
        class_name="Parameter",
        parent_class_id="CLS-META-CONCEPT-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A parameter: voltage, current, frequency, "
                    "timing value.",
    ),
    ClassSeed(
        class_id="CLS-OBC-CONSTRAINT",
        class_name="Constraint",
        parent_class_id="CLS-META-CONCEPT-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A constraint or requirement that must be "
                    "satisfied (e.g., over-voltage protection).",
    ),
    ClassSeed(
        class_id="CLS-OBC-PROTOCOL",
        class_name="Protocol",
        parent_class_id="CLS-META-CONCEPT-ENTITY",
        layer=LAYER_DOMAIN,
        domain=CURRENT_DOMAIN,
        description="A communication protocol (CAN, LIN, FlexRay, "
                    "or a charging protocol).",
    ),
)


ALL_SEEDS: tuple[ClassSeed, ...] = META_SEEDS + OBC_SEEDS


def seed_core_classes(conn: sqlite3.Connection) -> int:
    """Insert the core class seeds. Idempotent.

    Returns the number of classes newly created (existing seeds
    are skipped).
    """
    ensure_schema(conn)
    created = 0
    for seed in ALL_SEEDS:
        if get_class(conn, seed.class_id) is not None:
            continue
        try:
            create_class(
                conn,
                class_id=seed.class_id,
                class_name=seed.class_name,
                parent_class_id=seed.parent_class_id,
                layer=seed.layer,
                domain=seed.domain,
                description=seed.description,
                is_core=True,
            )
        except ClassRegistryError as e:
            # Tolerate ordering edge cases: if a parent hasn't been
            # inserted yet, the create fails. Re-raise only on
            # non-ordering errors.
            msg = str(e).lower()
            if "does not exist" in msg or "cycle" in msg:
                raise
            raise
        created += 1
    return created
