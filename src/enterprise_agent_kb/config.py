from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
