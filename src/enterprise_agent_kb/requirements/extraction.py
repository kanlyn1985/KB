from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import RequirementRepository, utc_now


@dataclass(frozen=True)
class RequirementCandidate:
    candidate_id: str
    batch_id: str
    candidate_type: str
    status: str
    source_type: str
    source_id: str | None
    document_id: str | None
    fact_id: str | None
    evidence_id: str | None
    raw_text: str
    normalized_text: str
    suggested_atom_id: str | None
    suggested_profile_id: str | None
    operator: str | None
    value_numeric: float | None
    value_text: str | None
    unit: str | None
    condition_json: dict[str, Any]
    confidence: float
    promoted_variant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "batch_id": self.batch_id,
            "candidate_type": self.candidate_type,
            "status": self.status,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "document_id": self.document_id,
            "fact_id": self.fact_id,
            "evidence_id": self.evidence_id,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "suggested_atom_id": self.suggested_atom_id,
            "suggested_profile_id": self.suggested_profile_id,
            "operator": self.operator,
            "value_numeric": self.value_numeric,
            "value_text": self.value_text,
            "unit": self.unit,
            "condition_json": self.condition_json,
            "confidence": self.confidence,
            "promoted_variant_id": self.promoted_variant_id,
        }


class RequirementExtractionService:
    """Rule-first candidate extractor for requirement texts.

    v9 deliberately creates review candidates only. It never activates a requirement
    variant until a user promotes a candidate into a selected RequirementProfile.
    """

    ATOM_RULES: tuple[dict[str, Any], ...] = (
        # --- DCDC electrical parameters (original MVP rules) ---
        {
            "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE",
            "aliases": ("输出纹波", "纹波电压", "纹波", "output ripple", "ripple"),
            "default_unit": "mV",
            "parameter_name": "output_ripple",
        },
        {
            "atom_id": "REQATOM-DCDC-EFFICIENCY",
            "aliases": ("满载效率", "效率", "efficiency"),
            "default_unit": "%",
            "parameter_name": "efficiency",
        },
        {
            "atom_id": "REQATOM-DCDC-SLEEP-CURRENT",
            "aliases": ("休眠电流", "静态电流", "sleep current"),
            "default_unit": "mA",
            "parameter_name": "sleep_current",
        },
        # --- CCU VAVE spec: signal detection (SC41003) ---
        {
            "atom_id": "REQATOM-CCU-CC-CP-DETECT",
            "aliases": ("CC 和CP 信号检测", "CC/CP 信号", "CC CP 检测", "CC和CP"),
            "default_unit": "V",
            "parameter_name": "cc_cp_signal_detect",
        },
        # --- CCU VAVE spec: V2L/V2V capability (SC41011) ---
        {
            "atom_id": "REQATOM-CCU-V2L-V2V-CAPABILITY",
            "aliases": ("V2L/V2V 能力", "V2L V2V", "V2L能力", "V2V能力", "V2L/V2V"),
            "default_unit": None,
            "parameter_name": "v2l_v2v_capability",
        },
        # --- CCU VAVE spec: network management wakeup/sleep (SC03003) ---
        {
            "atom_id": "REQATOM-CCU-NM-WAKEUP-SLEEP",
            "aliases": ("主动唤醒网络和休眠", "网络管理唤醒", "NM 唤醒", "同步唤醒和休眠", "CAN NM"),
            "default_unit": "ms",
            "parameter_name": "nm_wakeup_sleep",
        },
        # --- CCU VAVE spec: OBC charge control ---
        {
            "atom_id": "REQATOM-CCU-OBC-STOP-CHARGE",
            "aliases": ("OBC 停止充电", "停止充电", "OBC停止", "stop charging"),
            "default_unit": None,
            "parameter_name": "obc_stop_charge",
        },
        {
            "atom_id": "REQATOM-CCU-OBC-OUTPUT-POWER",
            "aliases": ("OBC 输出功率", "输出功率", "OBC功率", "output power"),
            "default_unit": "kW",
            "parameter_name": "obc_output_power",
        },
        # --- CCU VAVE spec: DCDC discharge control (SC44040/SC44034) ---
        {
            "atom_id": "REQATOM-CCU-DCDC-ACTIVE-DISCHARGE",
            "aliases": ("DCDC 主动放电", "主动放电", "Active discharge", "active discharge"),
            "default_unit": "ms",
            "parameter_name": "dcdc_active_discharge",
        },
        {
            "atom_id": "REQATOM-CCU-DCDC-DISCHARGE-MODE",
            "aliases": ("放电模式管理", "discharge 模式", "discharge mode"),
            "default_unit": None,
            "parameter_name": "dcdc_discharge_mode",
        },
        # --- CCU VAVE spec: DCDC mode management (SC44019/SC44004/SC44009/SC44017/SC44024) ---
        {
            "atom_id": "REQATOM-CCU-DCDC-BOOST-MODE",
            "aliases": ("Boost 模式管理", "Boost 模式", "Boost control", "boost mode"),
            "default_unit": None,
            "parameter_name": "dcdc_boost_mode",
        },
        {
            "atom_id": "REQATOM-CCU-DCDC-BUCK-MODE",
            "aliases": ("Buck 模式管理", "Buck 模式", "buck mode"),
            "default_unit": None,
            "parameter_name": "dcdc_buck_mode",
        },
        {
            "atom_id": "REQATOM-CCU-DCDC-INIT-MODE",
            "aliases": ("INIT 模式", "INIT 模式默认状态", "init mode"),
            "default_unit": None,
            "parameter_name": "dcdc_init_mode",
        },
        {
            "atom_id": "REQATOM-CCU-DCDC-READY-MODE",
            "aliases": ("Ready 模式管理", "Ready 模式", "ready mode"),
            "default_unit": None,
            "parameter_name": "dcdc_ready_mode",
        },
        {
            "atom_id": "REQATOM-CCU-DCDC-STANDBY-MODE",
            "aliases": ("Standby 模式管理", "Standby 模式", "standby mode"),
            "default_unit": None,
            "parameter_name": "dcdc_standby_mode",
        },
        {
            "atom_id": "REQATOM-CCU-DCDC-MODE-REQUEST",
            "aliases": ("模式请求管理", "模式请求", "mode request"),
            "default_unit": None,
            "parameter_name": "dcdc_mode_request",
        },
        # --- CCU VAVE spec: crash protection power-down (SC44023) ---
        {
            "atom_id": "REQATOM-CCU-CRASH-POWER-DOWN",
            "aliases": ("碰撞保护下电", "碰撞下电", "crash protection", "crash power down"),
            "default_unit": "ms",
            "parameter_name": "crash_power_down",
        },
        # --- CCU VAVE spec: electronic lock (SC40045/SC41015) ---
        {
            "atom_id": "REQATOM-CCU-ELECTRONIC-LOCK",
            "aliases": ("电子锁上锁", "执行电子锁", "electronic lock", "e-lock"),
            "default_unit": None,
            "parameter_name": "electronic_lock",
        },
        # --- CCU VAVE spec: security vulnerability (SC7000024) ---
        {
            "atom_id": "REQATOM-CCU-VULNERABILITY-UPGRADE",
            "aliases": ("漏洞升级", "漏洞", "vulnerability upgrade", "vulnerability"),
            "default_unit": None,
            "parameter_name": "vulnerability_upgrade",
        },
        # --- CCU VAVE spec: PT-CAN communication fault (SC40053) ---
        {
            "atom_id": "REQATOM-CCU-PTCAN-FAULT-RESPONSE",
            "aliases": ("PT-CAN 通讯故障", "PT-CAN 故障", "通讯故障响应", "PT-CAN fault"),
            "default_unit": None,
            "parameter_name": "ptcan_fault_response",
        },
        # --- CCU VAVE spec: sentinel power optimization ---
        {
            "atom_id": "REQATOM-CCU-SENTINEL-POWER",
            "aliases": ("哨兵功耗优化", "哨兵待命", "sentinel power", "sentinel"),
            "default_unit": "mA",
            "parameter_name": "sentinel_power",
        },
    )

    REQUIREMENT_MARKERS = (
        "应", "必须", "不得", "不应", "需", "需要", "要求", "shall", "must", "should", "require"
    )

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    @classmethod
    def from_root(cls, root: Path) -> "RequirementExtractionService":
        return cls(RequirementRepository(root))

    def extract_from_text(
        self,
        text: str,
        *,
        source_type: str = "manual_text",
        source_id: str | None = None,
        profile_id: str | None = None,
        document_id: str | None = None,
        fact_id: str | None = None,
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        self.repo.initialize_schema()
        now = utc_now()
        batch_id = self._new_id("RCB")
        sentences = self._split_requirement_sentences(text)
        candidates: list[RequirementCandidate] = []
        for index, sentence in enumerate(sentences, start=1):
            candidate = self._build_candidate(
                sentence,
                batch_id=batch_id,
                index=index,
                source_type=source_type,
                source_id=source_id,
                profile_id=profile_id,
                document_id=document_id,
                fact_id=fact_id,
                evidence_id=evidence_id,
            )
            if candidate:
                candidates.append(candidate)

        with self.repo._conn_ctx() as connection:
            connection.execute(
                """
                INSERT INTO requirement_candidate_batches (
                    batch_id, source_type, source_id, profile_id, document_id,
                    status, candidate_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, source_type, source_id, profile_id, document_id, "pending_review", len(candidates), now, now),
            )
            for candidate in candidates:
                connection.execute(
                    """
                    INSERT INTO requirement_candidates (
                        candidate_id, batch_id, candidate_type, status, source_type, source_id,
                        document_id, fact_id, evidence_id, raw_text, normalized_text,
                        suggested_atom_id, suggested_profile_id, operator, value_numeric,
                        value_text, unit, condition_json, confidence, promoted_variant_id,
                        review_note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.candidate_id,
                        candidate.batch_id,
                        candidate.candidate_type,
                        candidate.status,
                        candidate.source_type,
                        candidate.source_id,
                        candidate.document_id,
                        candidate.fact_id,
                        candidate.evidence_id,
                        candidate.raw_text,
                        candidate.normalized_text,
                        candidate.suggested_atom_id,
                        candidate.suggested_profile_id,
                        candidate.operator,
                        candidate.value_numeric,
                        candidate.value_text,
                        candidate.unit,
                        json.dumps(candidate.condition_json, ensure_ascii=False, sort_keys=True),
                        candidate.confidence,
                        candidate.promoted_variant_id,
                        None,
                        now,
                        now,
                    ),
                )
            self._insert_event(connection, batch_id, "batch_created", "extractor", f"{len(candidates)} candidates extracted")
            connection.commit()

        return {
            "batch_id": batch_id,
            "source_type": source_type,
            "source_id": source_id,
            "profile_id": profile_id,
            "candidate_count": len(candidates),
            "candidates": [candidate.to_dict() for candidate in candidates],
        }

    def extract_from_facts(self, *, doc_id: str | None = None, profile_id: str | None = None, limit: int = 500) -> dict[str, Any]:
        """Extract candidates from KB1 facts, preserving per-fact provenance.

        Each fact is extracted individually so the resulting candidates retain
        their source fact_id. Evidence linkage is resolved via the
        fact_evidence_map table, enabling Phase 5 graph fusion (supported_by
        Evidence relations).
        """
        self.repo.initialize_schema()
        where = "WHERE (fact_status IS NULL OR fact_status != 'quarantined_orphan')"
        params: list[Any] = []
        if doc_id:
            where += " AND source_doc_id = ?"
            params.append(doc_id)
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                f"""
                SELECT fact_id, source_doc_id, object_value, predicate, fact_type
                FROM facts
                {where}
                ORDER BY fact_type ASC, fact_id ASC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
            # Pre-fetch evidence_id mapping for all facts in one query.
            fact_ids = [row["fact_id"] for row in rows]
            ev_map: dict[str, str | None] = {}
            if fact_ids:
                placeholders = ",".join("?" for _ in fact_ids)
                ev_rows = connection.execute(
                    f"SELECT fact_id, evidence_id FROM fact_evidence_map WHERE fact_id IN ({placeholders})",
                    fact_ids,
                ).fetchall()
                for er in ev_rows:
                    # Keep first evidence_id per fact (one-to-many; first is fine for provenance).
                    if er["fact_id"] not in ev_map:
                        ev_map[er["fact_id"]] = er["evidence_id"]
        # Extract per-fact, sharing one batch_id.
        now = utc_now()
        batch_id = self._new_id("RCB")
        all_candidates: list[RequirementCandidate] = []
        for row in rows:
            raw = row["object_value"] or row["predicate"] or ""
            text = self._extract_text_from_object_value(raw)
            if not text:
                continue
            fact_id = row["fact_id"]
            evidence_id = ev_map.get(fact_id)
            sentences = self._split_requirement_sentences(text)
            for index, sentence in enumerate(sentences, start=1):
                candidate = self._build_candidate(
                    sentence,
                    batch_id=batch_id,
                    index=len(all_candidates) + 1,
                    source_type="facts",
                    source_id=doc_id,
                    profile_id=profile_id,
                    document_id=doc_id,
                    fact_id=fact_id,
                    evidence_id=evidence_id,
                )
                if candidate:
                    all_candidates.append(candidate)
        # Persist batch + candidates.
        with self.repo._conn_ctx() as connection:
            connection.execute(
                """
                INSERT INTO requirement_candidate_batches (
                    batch_id, source_type, source_id, profile_id, document_id,
                    status, candidate_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, "facts", doc_id, profile_id, doc_id, "pending_review", len(all_candidates), now, now),
            )
            for candidate in all_candidates:
                connection.execute(
                    """
                    INSERT INTO requirement_candidates (
                        candidate_id, batch_id, candidate_type, status, source_type, source_id,
                        document_id, fact_id, evidence_id, raw_text, normalized_text,
                        suggested_atom_id, suggested_profile_id, operator, value_numeric,
                        value_text, unit, condition_json, confidence, promoted_variant_id,
                        review_note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.candidate_id,
                        candidate.batch_id,
                        candidate.candidate_type,
                        candidate.status,
                        candidate.source_type,
                        candidate.source_id,
                        candidate.document_id,
                        candidate.fact_id,
                        candidate.evidence_id,
                        candidate.raw_text,
                        candidate.normalized_text,
                        candidate.suggested_atom_id,
                        candidate.suggested_profile_id,
                        candidate.operator,
                        candidate.value_numeric,
                        candidate.value_text,
                        candidate.unit,
                        json.dumps(candidate.condition_json, ensure_ascii=False, sort_keys=True),
                        candidate.confidence,
                        candidate.promoted_variant_id,
                        None,
                        now,
                        now,
                    ),
                )
            self._insert_event(connection, batch_id, "batch_created", "extractor", f"{len(all_candidates)} candidates extracted from {len(rows)} facts")
            connection.commit()
        return {
            "batch_id": batch_id,
            "source_type": "facts",
            "source_id": doc_id,
            "profile_id": profile_id,
            "candidate_count": len(all_candidates),
            "candidates": [candidate.to_dict() for candidate in all_candidates[:20]],
            "facts_scanned": len(rows),
            "facts_with_evidence": sum(1 for row in rows if row["fact_id"] in ev_map),
        }

    def list_candidates(
        self,
        *,
        batch_id: str | None = None,
        status: str | None = None,
        profile_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        self.repo.initialize_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if profile_id:
            clauses.append("suggested_profile_id = ?")
            params.append(profile_id)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM requirement_candidates
                {where}
                ORDER BY created_at DESC, candidate_id ASC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        candidates = [self._candidate_from_row(row).to_dict() for row in rows]
        return {
            "batch_id": batch_id,
            "status": status,
            "profile_id": profile_id,
            "candidate_count": len(candidates),
            "candidates": candidates,
        }

    def promote_candidate(
        self,
        candidate_id: str,
        *,
        profile_id: str | None = None,
        promoted_by: str | None = None,
    ) -> dict[str, Any]:
        self.repo.initialize_schema()
        now = utc_now()
        with self.repo._conn_ctx() as connection:
            row = connection.execute("SELECT * FROM requirement_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown candidate_id: {candidate_id}")
            candidate = self._candidate_from_row(row)
            if candidate.status == "promoted" and candidate.promoted_variant_id:
                return {"status": "already_promoted", "candidate": candidate.to_dict(), "variant_id": candidate.promoted_variant_id}
            if candidate.status not in {"pending_review", "rejected"}:
                raise ValueError(f"candidate {candidate_id} cannot be promoted from status {candidate.status}")
            target_profile_id = profile_id or candidate.suggested_profile_id
            if not candidate.suggested_atom_id:
                raise ValueError(f"candidate {candidate_id} has no suggested_atom_id")
            if not target_profile_id:
                raise ValueError(f"candidate {candidate_id} has no profile_id; pass --profile-id")
            atom = self.repo.load_atom(candidate.suggested_atom_id)
            variant_id = self._variant_id_for_candidate(candidate_id)
            connection.execute(
                """
                INSERT INTO requirement_variants (
                    variant_id, atom_id, profile_id, requirement_text, parameter_name,
                    operator, value_numeric, value_text, unit, condition_json,
                    requirement_type, mandatory_level, priority, source_type, source_id,
                    evidence_id, fact_id, document_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(variant_id) DO UPDATE SET
                    profile_id=excluded.profile_id,
                    requirement_text=excluded.requirement_text,
                    operator=excluded.operator,
                    value_numeric=excluded.value_numeric,
                    value_text=excluded.value_text,
                    unit=excluded.unit,
                    condition_json=excluded.condition_json,
                    evidence_id=excluded.evidence_id,
                    fact_id=excluded.fact_id,
                    document_id=excluded.document_id,
                    status='active',
                    updated_at=excluded.updated_at
                """,
                (
                    variant_id,
                    candidate.suggested_atom_id,
                    target_profile_id,
                    candidate.normalized_text,
                    atom.parameter_name,
                    candidate.operator,
                    candidate.value_numeric,
                    candidate.value_text,
                    candidate.unit or atom.default_unit,
                    json.dumps(candidate.condition_json, ensure_ascii=False, sort_keys=True),
                    "limit" if candidate.value_numeric is not None else "textual",
                    "customer_mandatory",
                    100,
                    "candidate",
                    candidate_id,
                    candidate.evidence_id,
                    candidate.fact_id,
                    candidate.document_id,
                    "active",
                    now,
                    now,
                ),
            )
            if candidate.evidence_id:
                binding_id = f"REB-CAND-{candidate_id}"
                connection.execute(
                    """
                    INSERT OR REPLACE INTO requirement_evidence_bindings (
                        binding_id, atom_id, variant_id, override_id, effective_id,
                        evidence_id, fact_id, document_id, page_no, block_id,
                        binding_type, confidence, created_at
                    ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        binding_id,
                        candidate.suggested_atom_id,
                        variant_id,
                        candidate.evidence_id,
                        candidate.fact_id,
                        candidate.document_id,
                        "candidate_promotion",
                        candidate.confidence,
                        now,
                    ),
                )
            connection.execute(
                """
                UPDATE requirement_candidates
                SET status = 'promoted', promoted_variant_id = ?, suggested_profile_id = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (variant_id, target_profile_id, now, candidate_id),
            )
            self._insert_event(connection, candidate.batch_id, "candidate_promoted", promoted_by, f"{candidate_id} -> {variant_id}")
            connection.commit()
        promoted = self.get_candidate(candidate_id)
        return {"status": "promoted", "variant_id": variant_id, "candidate": promoted}

    def reject_candidate(self, candidate_id: str, *, reviewer: str | None = None, reason: str | None = None) -> dict[str, Any]:
        self.repo.initialize_schema()
        now = utc_now()
        with self.repo._conn_ctx() as connection:
            row = connection.execute("SELECT * FROM requirement_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown candidate_id: {candidate_id}")
            connection.execute(
                """
                UPDATE requirement_candidates
                SET status = 'rejected', review_note = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (reason, now, candidate_id),
            )
            self._insert_event(connection, row["batch_id"], "candidate_rejected", reviewer, f"{candidate_id}: {reason or ''}")
            connection.commit()
        return {"status": "rejected", "candidate": self.get_candidate(candidate_id)}

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self.repo._conn_ctx() as connection:
            row = connection.execute("SELECT * FROM requirement_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown candidate_id: {candidate_id}")
        return self._candidate_from_row(row).to_dict()

    def _build_candidate(
        self,
        sentence: str,
        *,
        batch_id: str,
        index: int,
        source_type: str,
        source_id: str | None,
        profile_id: str | None,
        document_id: str | None,
        fact_id: str | None,
        evidence_id: str | None,
    ) -> RequirementCandidate | None:
        normalized = self._normalize_text(sentence)
        if not normalized:
            return None
        atom_id, atom_confidence = self._suggest_atom(normalized)
        parsed = self._parse_numeric_constraint(normalized)
        if atom_id is None and parsed.get("value_numeric") is None:
            return None
        confidence = 0.45 + atom_confidence
        if parsed.get("value_numeric") is not None:
            confidence += 0.25
        if evidence_id:
            confidence += 0.1
        confidence = min(confidence, 0.95)
        return RequirementCandidate(
            candidate_id=f"RCAND-{batch_id[4:]}-{index:03d}",
            batch_id=batch_id,
            candidate_type="variant",
            status="pending_review",
            source_type=source_type,
            source_id=source_id,
            document_id=document_id,
            fact_id=fact_id,
            evidence_id=evidence_id,
            raw_text=sentence.strip(),
            normalized_text=normalized,
            suggested_atom_id=atom_id,
            suggested_profile_id=profile_id,
            operator=parsed.get("operator"),
            value_numeric=parsed.get("value_numeric"),
            value_text=parsed.get("value_text"),
            unit=parsed.get("unit"),
            condition_json=parsed.get("condition_json") or {},
            confidence=round(confidence, 3),
        )

    def _extract_text_from_object_value(self, raw: str) -> str:
        """Extract the richest text from a fact object_value.

        object_value may be plain text or a JSON object with title/content/
        subject fields. For JSON we prefer content (full requirement text)
        falling back to subject+title. For plain text we return as-is.
        """
        if not raw:
            return ""
        raw = raw.strip()
        # Try JSON parse for structured fact payloads
        if raw.startswith("{"):
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    parts = []
                    if obj.get("content"):
                        parts.append(str(obj["content"]))
                    elif obj.get("title"):
                        # title-only facts (section headings, TOC) are weaker
                        # but still useful for atom matching
                        parts.append(str(obj["title"]))
                    if obj.get("subject") and obj.get("subject") not in parts:
                        parts.append(str(obj["subject"]))
                    return " ".join(parts) if parts else ""
            except (json.JSONDecodeError, TypeError):
                pass
        return raw

    def _split_requirement_sentences(self, text: str) -> list[str]:
        raw_parts = re.split(r"[\n。；;]+", text or "")
        parts: list[str] = []
        for part in raw_parts:
            value = part.strip(" \t，,。；;")
            if not value:
                continue
            lowered = value.lower()
            if any(marker in lowered for marker in self.REQUIREMENT_MARKERS) or self._suggest_atom(value)[0]:
                parts.append(value)
        return parts

    def _suggest_atom(self, text: str) -> tuple[str | None, float]:
        lowered = text.lower()
        for rule in self.ATOM_RULES:
            for alias in rule["aliases"]:
                if alias.lower() in lowered:
                    return str(rule["atom_id"]), 0.25
        return None, 0.0

    def _parse_numeric_constraint(self, text: str) -> dict[str, Any]:
        operator = None
        if re.search(r"(≤|<=|不大于|小于等于|不超过|以下|不得超过|不高于)", text, flags=re.IGNORECASE):
            operator = "<="
        elif re.search(r"(≥|>=|不低于|大于等于|不小于|以上|至少)", text, flags=re.IGNORECASE):
            operator = ">="
        elif re.search(r"(<|小于)", text):
            operator = "<"
        elif re.search(r"(>|大于)", text):
            operator = ">"
        match = re.search(r"[≤≥<>＝=]*\s*(\d+(?:\.\d+)?)\s*(mv|mV|v|V|ma|mA|a|A|%|％|毫伏|伏|毫安|安)?", text)
        if not match:
            return {"operator": operator, "value_numeric": None, "value_text": None, "unit": None, "condition_json": self._parse_conditions(text)}
        raw_unit = match.group(2)
        return {
            "operator": operator,
            "value_numeric": float(match.group(1)),
            "value_text": None,
            "unit": self._normalize_unit(raw_unit),
            "condition_json": self._parse_conditions(text),
        }

    def _parse_conditions(self, text: str) -> dict[str, Any]:
        conditions: dict[str, Any] = {}
        temp = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:℃|°c|c)", text, flags=re.IGNORECASE)
        if temp:
            conditions["temperature"] = f"{temp.group(1)}C"
        if "满载" in text or "full load" in text.lower():
            conditions["load"] = "full_load"
        if "休眠" in text or "sleep" in text.lower():
            conditions["mode"] = "sleep"
        return conditions

    def _normalize_unit(self, unit: str | None) -> str | None:
        if not unit:
            return None
        aliases = {
            "mv": "mV", "毫伏": "mV", "v": "V", "伏": "V",
            "ma": "mA", "毫安": "mA", "a": "A", "安": "A", "％": "%", "%": "%",
        }
        return aliases.get(unit.strip().lower(), unit.strip())

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    def _new_id(self, prefix: str) -> str:
        token = re.sub(r"[^0-9A-Za-z]", "", utc_now())[-14:]
        return f"{prefix}-{token}"

    def _variant_id_for_candidate(self, candidate_id: str) -> str:
        suffix = re.sub(r"[^0-9A-Za-z-]", "-", candidate_id).replace("RCAND-", "")
        return f"REQVAR-CAND-{suffix}"

    def _insert_event(self, connection: sqlite3.Connection, batch_id: str, event_type: str, actor: str | None, comment: str | None) -> None:
        event_id = f"RCEVT-{re.sub(r'[^0-9A-Za-z]', '', utc_now())[-14:]}-{event_type}"
        connection.execute(
            """
            INSERT INTO requirement_candidate_events (event_id, batch_id, candidate_id, event_type, actor, comment, created_at)
            VALUES (?, ?, NULL, ?, ?, ?, ?)
            """,
            (event_id, batch_id, event_type, actor, comment, utc_now()),
        )

    def _candidate_from_row(self, row: sqlite3.Row) -> RequirementCandidate:
        condition_raw = row["condition_json"]
        return RequirementCandidate(
            candidate_id=row["candidate_id"],
            batch_id=row["batch_id"],
            candidate_type=row["candidate_type"],
            status=row["status"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            document_id=row["document_id"],
            fact_id=row["fact_id"],
            evidence_id=row["evidence_id"],
            raw_text=row["raw_text"],
            normalized_text=row["normalized_text"],
            suggested_atom_id=row["suggested_atom_id"],
            suggested_profile_id=row["suggested_profile_id"],
            operator=row["operator"],
            value_numeric=row["value_numeric"],
            value_text=row["value_text"],
            unit=row["unit"],
            condition_json=json.loads(condition_raw) if condition_raw else {},
            confidence=float(row["confidence"] or 0.0),
            promoted_variant_id=row["promoted_variant_id"],
        )
