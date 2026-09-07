# -*- coding: utf-8 -*-
"""V0.8 Hypothesis runtime（AKB-V08-IMPL-001）。"""
from agent_kb.hypothesis.runtime import (
    Hypothesis,
    HypothesisError,
    HypothesisService,
    hypothesis_identity,
)

from agent_kb.hypothesis.verification import (  # noqa: E402
    VerificationTask,
    VerificationTaskError,
    VerificationTaskRuntime,
    verification_task_identity,
)

from agent_kb.hypothesis.verdict import (  # noqa: E402
    Verdict,
    VerdictError,
    VerdictRuntime,
    verdict_identity,
)

from agent_kb.hypothesis.evolution import (  # noqa: E402
    EvolutionView,
    EvolutionViewError,
    EvolutionViewRuntime,
)

__all__ = ["Hypothesis", "HypothesisError", "HypothesisService",
           "hypothesis_identity", "VerificationTask",
           "VerificationTaskError", "VerificationTaskRuntime",
           "verification_task_identity", "Verdict", "VerdictError",
           "VerdictRuntime", "verdict_identity", "EvolutionView",
           "EvolutionViewError", "EvolutionViewRuntime"]