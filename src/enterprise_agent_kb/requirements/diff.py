from __future__ import annotations

from pathlib import Path

from .comparator import RequirementComparator
from .repository import RequirementRepository
from .resolver import RequirementResolver


class RequirementDiffService:
    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self.resolver = RequirementResolver(repo)
        self.comparator = RequirementComparator()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementDiffService":
        return cls(RequirementRepository(root))

    def diff_project_against_profile(self, project_id: str, base_profile_id: str) -> dict[str, object]:
        project_effective = self.resolver.resolve_project(project_id)
        base_profile = self.repo.load_profile(base_profile_id)
        base_atoms = self.repo.load_atoms_for_profiles([base_profile_id])
        base_by_atom = {}
        for atom in base_atoms:
            variants = self.repo.load_variants(atom.atom_id, [base_profile_id])
            if variants:
                base_by_atom[atom.atom_id] = (atom, sorted(variants, key=lambda v: (v.priority, v.variant_id))[0])

        result: dict[str, list[dict[str, object]]] = {
            "added": [],
            "tightened": [],
            "loosened": [],
            "replaced": [],
            "same": [],
            "ambiguous": [],
        }

        for effective in project_effective:
            base = base_by_atom.get(effective.atom_id)
            if base is None:
                result["added"].append(effective.to_dict())
                continue
            atom, base_variant = base
            current_variants = self.repo.load_variants(effective.atom_id, [base_profile_id])
            project_variant = None
            if effective.selected_variant_id:
                # Reuse all profiles from project and pick the selected variant by id.
                project_profile = self.repo.find_project_profile(project_id)
                if project_profile:
                    profiles = self.repo.expand_profile_inheritance(project_profile.profile_id)
                    candidates = self.repo.load_variants(effective.atom_id, [p.profile_id for p in profiles])
                    project_variant = next((v for v in candidates if v.variant_id == effective.selected_variant_id), None)
            if not project_variant:
                result["ambiguous"].append(effective.to_dict())
                continue
            compare = self.comparator.compare(atom, base_variant, project_variant)
            bucket = {
                "tighten": "tightened",
                "loosen": "loosened",
                "replace": "replaced",
                "clarify": "replaced",
                "same": "same",
            }.get(compare.effect, "ambiguous")
            result[bucket].append(
                {
                    "atom_id": effective.atom_id,
                    "base_profile_id": base_profile.profile_id,
                    "base_requirement": base_variant.requirement_text,
                    "project_requirement": effective.effective_requirement_text,
                    "effect": compare.effect,
                    "reason": compare.reason,
                    "conflict_status": effective.conflict_status,
                }
            )
        return {
            "project_id": project_id,
            "base_profile_id": base_profile_id,
            "base_profile_name": base_profile.name,
            "diff": result,
        }
