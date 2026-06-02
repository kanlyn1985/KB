from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppEndpoints:
    """Centralized default endpoints for external vendor APIs.

    Each field documents the env var that overrides it at runtime; production
    deployments typically set those env vars directly, so this class is mainly
    useful for tests and as a single place to read the defaults.
    """
    minimax_api_host: str
    """MiniMax (海螺 AI) OpenAI-compatible endpoint. Env: MINIMAX_API_HOST."""
    minimax_anthropic_base: str
    """MiniMax's Anthropic-compatible mirror. Env: MINIMAX_ANTHROPIC_BASE_URL."""
    anthropic_base_url: str
    """Anthropic-compatible endpoint (default routes through MaaS coding gateway). Env: ANTHROPIC_BASE_URL."""
    openai_api_base: str
    """OpenAI-compatible endpoint. Env: OPENAI_API_BASE."""
    astron_api_base: str
    """ASTRON (讯飞 Astron) endpoint on the MaaS coding gateway. Env: ASTRON_API_BASE."""

    @classmethod
    def from_env(cls) -> "AppEndpoints":
        return cls(
            minimax_api_host=os.environ.get("MINIMAX_API_HOST", "https://api.minimaxi.com"),
            minimax_anthropic_base=os.environ.get(
                "MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic"
            ),
            anthropic_base_url=os.environ.get(
                "ANTHROPIC_BASE_URL",
                "https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic",
            ),
            openai_api_base=os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
            astron_api_base=os.environ.get(
                "ASTRON_API_BASE", "https://maas-coding-api.cn-huabei-1.xf-yun.com"
            ),
        )


@dataclass(frozen=True)
class AppPaths:
    root: Path
    raw: Path
    normalized: Path
    evidence: Path
    facts: Path
    wiki: Path
    coverage_reports: Path
    review_queue: Path
    quality_reports: Path
    logs: Path
    db_dir: Path
    db_file: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        root = root.resolve()
        db_dir = root / "db"
        return cls(
            root=root,
            raw=root / "raw",
            normalized=root / "normalized",
            evidence=root / "evidence",
            facts=root / "facts",
            wiki=root / "wiki",
            coverage_reports=root / "coverage_reports",
            review_queue=root / "review_queue",
            quality_reports=root / "quality_reports",
            logs=root / "logs",
            db_dir=db_dir,
            db_file=db_dir / "knowledge.db",
        )

    def all_dirs(self) -> list[Path]:
        return [
            self.root,
            self.raw,
            self.normalized,
            self.evidence,
            self.facts,
            self.wiki,
            self.coverage_reports,
            self.review_queue,
            self.quality_reports,
            self.logs,
            self.db_dir,
        ]
