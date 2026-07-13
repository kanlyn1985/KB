from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .comparator import RequirementComparator
from .models import (
    EffectiveRequirement,
    RequirementAtom,
    RequirementOverride,
    RequirementProfile,
    RequirementVariant,
    ResolutionStep,
)
from .repository import RequirementRepository


@dataclass
class ResolutionState:
    project_id: str
    atom: RequirementAtom
    selected_variant: RequirementVariant | None = None
    steps: list[ResolutionStep] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    approval_required: bool = False

    def add_step(
        self,
        profile: RequirementProfile,
        variant: RequirementVariant | None,
        effect: str,
        conflict_status: str = "none",
    ) -> None:
        self.steps.append(
            ResolutionStep(
                profile_id=profile.profile_id,
                profile_type=profile.profile_type,
                variant_id=variant.variant_id if variant else None,
                requirement_text=variant.requirement_text if variant else None,
                effect=effect,
                conflict_status=conflict_status,
                evidence_id=variant.evidence_id if variant else None,
            )
        )
        if conflict_status != "none":
            self.conflicts.append(conflict_status)


class RequirementResolver:
    def __init__(self, repo: RequirementRepository, comparator: RequirementComparator | None = None):
        self.repo = repo
        self.comparator = comparator or RequirementComparator()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementResolver":
        return cls(RequirementRepository(root))

    def resolve_requirement(self, project_id: str, atom_id: str) -> EffectiveRequirement:
        project_profile = self.repo.find_project_profile(project_id)
        if project_profile is None:
            raise ValueError(f"project has no requirement profile: {project_id}")

        atom = self.repo.load_atom(atom_id)
        profiles = self.repo.expand_profile_inheritance(project_profile.profile_id)
        profile_ids = [profile.profile_id for profile in profiles]
        variants = self.repo.load_variants(atom_id=atom_id, profile_ids=profile_ids)
        overrides = self.repo.load_overrides(atom_id=atom_id, profile_ids=profile_ids)
        by_profile = {profile.profile_id: [] for profile in profiles}
        for variant in variants:
            by_profile.setdefault(variant.profile_id, []).append(variant)

        override_by_profile = {profile.profile_id: [] for profile in profiles}
        for override in overrides:
            override_by_profile.setdefault(override.profile_id, []).append(override)

        state = ResolutionState(project_id=project_id, atom=atom)
        for profile in profiles:
            state = self._apply_layer(
                state,
                profile,
                by_profile.get(profile.profile_id, []),
                override_by_profile.get(profile.profile_id, []),
            )

        effective = self._to_effective(state)
        self.repo.save_effective_requirement(effective)
        return effective

    def resolve_project(self, project_id: str) -> list[EffectiveRequirement]:
        project_profile = self.repo.find_project_profile(project_id)
        if project_profile is None:
            raise ValueError(f"project has no requirement profile: {project_id}")
        profiles = self.repo.expand_profile_inheritance(project_profile.profile_id)
        atoms = self.repo.load_atoms_for_profiles([profile.profile_id for profile in profiles])
        return [self.resolve_requirement(project_id, atom.atom_id) for atom in atoms]

    def _apply_layer(
        self,
        state: ResolutionState,
        profile: RequirementProfile,
        variants: list[RequirementVariant],
        overrides: list[RequirementOverride],
    ) -> ResolutionState:
        active_variants = sorted(variants, key=lambda variant: (variant.priority, variant.variant_id))
        if len(active_variants) > 1:
            state.conflicts.append("ambiguous")

        selected = active_variants[0] if active_variants else None
        if selected is None:
            return state

        if state.selected_variant is None:
            state.selected_variant = selected
            state.add_step(profile, selected, "base_constraint")
            return state

        compare = self.comparator.compare(state.atom, state.selected_variant, selected)
        conflict_status = self._conflict_for_effect(state.selected_variant, selected, compare.effect, overrides)
        if compare.effect in {"tighten", "loosen", "replace", "clarify"}:
            state.selected_variant = selected
        state.add_step(profile, selected, compare.effect, conflict_status=conflict_status)
        return state

    def _conflict_for_effect(
        self,
        parent: RequirementVariant,
        child: RequirementVariant,
        effect: str,
        overrides: list[RequirementOverride],
    ) -> str:
        if effect not in {"loosen", "replace"}:
            return "none"
        if parent.mandatory_level == "mandatory" and effect == "loosen":
            return "hard_blocker"
        if effect == "loosen":
            approved = any(
                override.approval_status == "approved"
                and override.new_variant_id == child.variant_id
                for override in overrides
            )
            return "none" if approved else "approval_required"
        return "none"

    def _to_effective(self, state: ResolutionState) -> EffectiveRequirement:
        selected = state.selected_variant
        if selected is None:
            return EffectiveRequirement(
                project_id=state.project_id,
                atom_id=state.atom.atom_id,
                selected_variant_id=None,
                effective_requirement_text="",
                operator=None,
                value_numeric=None,
                value_text=None,
                unit=None,
                condition_json={},
                resolution_path=state.steps,
                conflict_status="ambiguous",
                verification_status="missing",
                approval_status="none",
                evidence_ids=[],
            )

        conflicts = [step.conflict_status for step in state.steps if step.conflict_status != "none"]
        conflict_status = self._dominant_conflict(conflicts)
        evidence_ids = [step.evidence_id for step in state.steps if step.evidence_id]
        verification_status = "verified" if selected.evidence_id or evidence_ids else "unverified"
        if conflict_status == "none" and verification_status == "unverified":
            conflict_status = "evidence_missing"
        approval_status = "required" if conflict_status == "approval_required" else "none"
        return EffectiveRequirement(
            project_id=state.project_id,
            atom_id=state.atom.atom_id,
            selected_variant_id=selected.variant_id,
            effective_requirement_text=selected.requirement_text,
            operator=selected.operator,
            value_numeric=selected.value_numeric,
            value_text=selected.value_text,
            unit=selected.unit,
            condition_json=selected.condition_json,
            resolution_path=state.steps,
            conflict_status=conflict_status,
            verification_status=verification_status,
            approval_status=approval_status,
            evidence_ids=[e for e in evidence_ids if e],
        )

    def _dominant_conflict(self, conflicts: list[str]) -> str:
        for status in ["hard_blocker", "approval_required", "evidence_missing", "ambiguous", "condition_conflict"]:
            if status in conflicts:
                return status
        return "none"
