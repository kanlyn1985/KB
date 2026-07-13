from __future__ import annotations

from .models import CompareResult, RequirementAtom, RequirementVariant


class RequirementComparator:
    def compare(
        self,
        atom: RequirementAtom,
        parent: RequirementVariant,
        child: RequirementVariant,
    ) -> CompareResult:
        if parent.value_numeric is None or child.value_numeric is None:
            return self._compare_text_or_condition(parent, child)

        if parent.unit and child.unit and parent.unit != child.unit:
            return CompareResult("ambiguous", f"unit mismatch: {parent.unit} vs {child.unit}", 0.2)

        if atom.constraint_kind == "max_limit":
            return self._compare_max_limit(parent, child)
        if atom.constraint_kind == "min_limit":
            return self._compare_min_limit(parent, child)
        if atom.constraint_kind == "range_tolerance":
            return self._compare_range_tolerance(parent, child)

        if parent.value_numeric == child.value_numeric:
            return self._compare_text_or_condition(parent, child)
        return CompareResult("replace", "numeric values differ for non-ordered constraint kind", 0.5)

    def _compare_max_limit(self, parent: RequirementVariant, child: RequirementVariant) -> CompareResult:
        assert parent.value_numeric is not None and child.value_numeric is not None
        if child.value_numeric < parent.value_numeric:
            return CompareResult("tighten", "lower maximum limit is stricter")
        if child.value_numeric > parent.value_numeric:
            return CompareResult("loosen", "higher maximum limit is looser")
        return self._compare_text_or_condition(parent, child)

    def _compare_min_limit(self, parent: RequirementVariant, child: RequirementVariant) -> CompareResult:
        assert parent.value_numeric is not None and child.value_numeric is not None
        if child.value_numeric > parent.value_numeric:
            return CompareResult("tighten", "higher minimum limit is stricter")
        if child.value_numeric < parent.value_numeric:
            return CompareResult("loosen", "lower minimum limit is looser")
        return self._compare_text_or_condition(parent, child)

    def _compare_range_tolerance(self, parent: RequirementVariant, child: RequirementVariant) -> CompareResult:
        assert parent.value_numeric is not None and child.value_numeric is not None
        if child.value_numeric < parent.value_numeric:
            return CompareResult("tighten", "narrower tolerance is stricter")
        if child.value_numeric > parent.value_numeric:
            return CompareResult("loosen", "wider tolerance is looser")
        return self._compare_text_or_condition(parent, child)

    def _compare_text_or_condition(self, parent: RequirementVariant, child: RequirementVariant) -> CompareResult:
        if parent.condition_json != child.condition_json:
            return CompareResult("clarify", "condition changed or clarified", 0.7)
        if parent.requirement_text.strip() == child.requirement_text.strip():
            return CompareResult("same", "same requirement text")
        return CompareResult("replace", "textual requirement differs", 0.5)
