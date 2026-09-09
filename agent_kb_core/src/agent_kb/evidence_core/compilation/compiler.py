# -*- coding: utf-8 -*-
"""L8 CandidateAssertionBuilder + SemanticCompiler（编排：指纹/幂等/事务/provenance）。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime

from agent_kb.evidence_core.assertions import AssertionStore, POLICY_VERSION, Provenance
from agent_kb.evidence_core.compilation.errors import (
    E_CANDIDATE_BUILD_FAILED,
    E_COMPILER_INVALID_EVIDENCE,
    E_COMPILATION_DUPLICATE,
    E_COMPILATION_PROVENANCE_MISSING,
    CompilationError,
    IdempotentHit,
)
from agent_kb.evidence_core.compilation.models import (
    CompilationResult,
    CompilationRunRecord,
    SemanticUnitRecord,
    canonical_json,
)
from agent_kb.evidence_core.compilation.providers import (
    BUILTIN_EXTRACTOR_VERSION,
    BuiltinRuleExtractor,
    SemanticCompilerProvider,
    validate_provider_output,
)
from agent_kb.evidence_core.compilation.resolvers import (
    EntityCandidateResolver,
    OntologyMapper,
    RelationCandidateResolver,
    TemporalParser,
)
from agent_kb.evidence_core.compilation.normalizer import (
    NORMALIZER_VERSION,
    Preprocessor,
    SemanticNormalizer,
)
from agent_kb.evidence_core.models import KnowledgeAssertion

COMPILER_VERSION = "v02-compiler-1.0"
BUILDER_VERSION = "builder-v1.0"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compilation_fingerprint(evidence_id: str, compiler_version: str,
                            configuration_hash: str, content_hash: str) -> str:
    """CanonicalJSON fingerprint（V0.2_DETERMINISM 正式定义，fingerprint_spec=v1）。"""
    payload = {
        "evidence_id": evidence_id,
        "compiler_version": compiler_version,
        "configuration_hash": configuration_hash,
        "content_hash": content_hash,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def configuration_hash(config: dict) -> str:
    from agent_kb.evidence_core.compilation.models import canonical_json as cj
    return hashlib.sha256(cj(config).encode("utf-8")).hexdigest()


class CandidateAssertionBuilder:
    """L8：SemanticUnit → KnowledgeAssertion(status=candidate)（唯一入口 create_candidate）。"""

    def __init__(self, store: AssertionStore):
        self.store = store

    def build(self, unit: SemanticUnitRecord, *, actor_id: str,
              ontology_scope: str, quarantined: bool) -> KnowledgeAssertion | None:
        if quarantined:
            return None  # quarantine unit不产 assertion（CMP-014）
        relations = unit.relation_candidates or []
        if not relations:
            return None  # 无可表达关系 → 无 assertion（合法）
        produced: list[KnowledgeAssertion] = []
        for rel in relations:
            subj = next((e for e in unit.entity_candidates
                         if e["candidate_id"] == rel["subject_candidate_id"]), None)
            obj = next((e for e in unit.entity_candidates
                        if e["candidate_id"] == rel["object_candidate_id"]), None)
            if subj is None or obj is None:
                raise CompilationError(E_CANDIDATE_BUILD_FAILED,
                                       f"orphan candidate ref in {unit.unit_id}")
            assertion_type = "extracted"
            derivation = None
            if unit.extraction_method.startswith("reasoner:"):
                assertion_type = "inferred"
                derivation = getattr(unit, "derivation", None) or unit.ontology_mapping.get(
                    "derivation") if isinstance(unit.ontology_mapping, dict) else None
                if not derivation or not all(derivation.get(k) for k in
                                             ("rule_ref", "parent_assertions", "reasoner_id")):
                    raise CompilationError(E_CANDIDATE_BUILD_FAILED,
                                           "inferred requires rule_ref/parent_assertions/reasoner_id")
            try:
                a = self.store.create_candidate(
                    subject_ref=f"entity:{subj['normalized_form']}",
                    predicate_ref=f"relation:{rel['predicate_candidate']}",
                    object={"kind": "literal", "value": obj["normalized_form"]},
                    assertion_type=assertion_type,
                    ontology_scope=ontology_scope,
                    actor_id=actor_id,
                    confidence=round(rel["confidence"], 4),
                    evidence_refs=[unit.evidence_id],
                    source_unit_refs=[unit.unit_id],
                    derivation=derivation)
            except LookupError as exc:  # evidence 引用问题
                raise CompilationError(E_CANDIDATE_BUILD_FAILED, str(exc)) from exc
            produced.append(a)
        return produced


class SemanticCompiler:
    """编排器：single-evidence；指纹幂等；run 单事务原子；provenance 三层留痕。"""

    POLICY = "policy:v0.2"

    def __init__(self, connection: sqlite3.Connection, *,
                 provider: SemanticCompilerProvider | None = None,
                 domain_pack=None, compiler_version: str = COMPILER_VERSION):
        self.connection = connection
        self.provider = provider or BuiltinRuleExtractor()
        self.domain_pack = domain_pack
        self.compiler_version = compiler_version
        self.pre = Preprocessor()
        self.normalizer = SemanticNormalizer()
        self.entity_resolver = EntityCandidateResolver()
        self.relation_resolver = RelationCandidateResolver()
        self.temporal_parser = TemporalParser()
        self.builder = CandidateAssertionBuilder(AssertionStore(connection))
        self.provenance = Provenance(connection)

    # ---- provenance 八问（CMP-009）----
    def describe_run(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM akb_compilation_runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def trace_assertion_compilation(self, assertion_id: str) -> dict:
        row = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id = ?", (assertion_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        unit = self.connection.execute(
            "SELECT * FROM akb_semantic_units WHERE unit_id = ?",
            (json_field(row, "source_unit_refs_json", 0),)).fetchone()
        run = None
        evidence = None
        if unit is not None:
            run = self.describe_run(unit["compiler_run_ref"]) if unit["compiler_run_ref"] else None
            evidence = self.connection.execute(
                "SELECT * FROM akb_evidence WHERE evidence_id = ?",
                (unit["evidence_id"],)).fetchone()
        return {
            "assertion": dict(row),
            "unit": dict(unit) if unit else None,
            "run": run,
            "evidence": dict(evidence) if evidence else None,
        }

    # ---- 主入口 ----
    def compile(self, evidence_id: str, *, actor_id: str,
                ontology_scope: str = "ontology:generic:0.1",
                config: dict | None = None) -> CompilationResult:
        # 单证据契约：compile(evidence_id) 恰一 Evidence（batch=V0.3+）
        cfg = dict(config or {})
        cfg.update({"compiler_version": self.compiler_version,
                    "provider": self.provider.provider_id(),
                    "normalizer": NORMALIZER_VERSION,
                    "ontology": getattr(self.domain_pack, "version", None)})
        cfg_hash = configuration_hash(cfg)

        if not isinstance(evidence_id, str) or not evidence_id.strip():
            # 单证据契约（CMP-021）：非 str（如 list）→ V0.2 拒绝，绝不进入持久层
            raise CompilationError(E_COMPILER_INVALID_EVIDENCE,
                                   "single-evidence contract: evidence_id must be one string")
        ev_row = self.connection.execute(
            "SELECT e.*, d.effective_at AS _document_effective_time"
            " FROM akb_evidence e LEFT JOIN akb_documents d ON d.document_id = e.document_id"
            " WHERE e.evidence_id = ?", (evidence_id,)).fetchone()
        if ev_row is None:
            raise CompilationError("E-COMPILER-INVALID-EVIDENCE", f"evidence not found: {evidence_id}")

        fp = compilation_fingerprint(evidence_id, self.compiler_version, cfg_hash,
                                     ev_row["content_hash"])
        # 幂等：fingerprint 命中 → 返回既有（E-COMPILATION-DUPLICATE 语义 = 幂等返回）
        hit = self.connection.execute(
            "SELECT unit_id FROM akb_semantic_units WHERE content_fingerprint = ?", (fp,)).fetchone()
        if hit:
            anchor = self.connection.execute(
                "SELECT * FROM akb_semantic_units WHERE content_fingerprint = ?", (fp,)).fetchone()
            run_row = self.connection.execute(
                "SELECT * FROM akb_compilation_runs WHERE run_id = ?",
                (anchor["compiler_run_ref"],)).fetchone() if anchor["compiler_run_ref"] else None
            # 幂等返回该次 compilation 的全部产物（同 run 全部 units——fingerprint 锚在 unit0）
            units = self.connection.execute(
                "SELECT * FROM akb_semantic_units WHERE compiler_run_ref = ?"
                " ORDER BY unit_id", (anchor["compiler_run_ref"],)).fetchall()
            assertions = self._assertions_for_units([u["unit_id"] for u in units])
            warnings = json.loads(run_row["warnings_json"]) if run_row else []
            return CompilationResult(
                run=CompilationRunRecord(**_run_kwargs(run_row)) if run_row else None,
                units=[self._unit_from_row(u) for u in units],
                assertions=assertions,
                warnings=warnings, fingerprint=fp, idempotent_hit=True)

        prov = self.provenance.record(actor_id=actor_id,
                                      actor_kind=_kind_of(actor_id), activity="compile",
                                      inputs=[evidence_id])
        if prov is None or not prov.provenance_id:
            raise CompilationError(E_COMPILATION_PROVENANCE_MISSING)
        run = CompilationRunRecord(
            run_id=f"run_{prov.provenance_id[5:]}", evidence_ids=[evidence_id],
            compiler_version=self.compiler_version, configuration_hash=cfg_hash,
            ontology_version=getattr(self.domain_pack, "version", None),
            provider_id=self.provider.provider_id(), actor_id=actor_id,
            policy_version=self.POLICY)
        self.connection.execute(
            "INSERT INTO akb_compilation_runs (run_id, evidence_ids_json, compiler_version,"
            " configuration_hash, ontology_version, provider_id, actor_id, policy_version, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')",
            (run.run_id, canonical_json(run.evidence_ids), run.compiler_version,
             run.configuration_hash, run.ontology_version, run.provider_id,
             run.actor_id, run.policy_version))

        sp = f"sp_comp_{run.run_id}"
        self.connection.execute(f"SAVEPOINT {sp}")
        try:
            evidence = type("E", (), {"evidence_id": ev_row["evidence_id"],
                                      "content": ev_row["content"]})()
            segments = self.pre.segment(evidence)
            units: list[SemanticUnitRecord] = []
            assertions: list[KnowledgeAssertion] = []
            warnings: list[str] = []
            quarantined_any = False
            for seg in segments:
                try:
                    norm = self.normalizer.normalize(seg)
                    raw = self.provider.extract(norm)
                    validate_provider_output(raw)
                    entities = self.entity_resolver.resolve(raw)
                    relations = self.relation_resolver.resolve(raw, entities)
                    if len(relations) < len(raw.relations_raw):
                        warnings.append(f"segment {seg.segment_id}: orphan relation refs dropped")
                    # T-02：相对时间锚 = akb_documents.effective_at（Defect A 修复；
                    # 严禁 datetime.now/time.time 进入语义时间计算）
                    tparse = self.temporal_parser.parse(
                        raw.temporal_expressions,
                        observation_time=ev_row["observed_at"],
                        document_effective_time=ev_row["_document_effective_time"],
                        ingestion_time=ev_row["created_at"])
                    mappings = OntologyMapper(self.domain_pack).map(entities, relations)
                    quarantined = any(m.mapping_status == "quarantined" for m in mappings)
                    quarantined_any = quarantined_any or quarantined
                    unit = SemanticUnitRecord(
                        unit_id=f"su_{prov.provenance_id[5:]}_{seg.segment_id[-4:]}",
                        evidence_id=evidence_id, unit_type=seg.block_type,
                        normalized_text=norm.normalized_text,
                        entity_candidates=[asdict(c) for c in entities],
                        relation_candidates=[asdict(c) for c in relations],
                        temporal_parse=asdict(tparse) if tparse else None,
                        ontology_mapping={"mappings": [asdict(m) for m in mappings]},
                        extraction_method=f"compiler:{self.provider.provider_id()}",
                        extraction_version=BUILTIN_EXTRACTOR_VERSION,
                        provenance_ref=prov.provenance_id, compiler_run_ref=run.run_id,
                        configuration_hash=cfg_hash,
                        # V0.2 fingerprint 锚语义（AKB-V02-IMPL-002 Defect B 显式化）：
                        # - CompilationFingerprint 标识一次 compilation invocation；
                        # - 首个 SemanticUnit 持 fingerprint 为持久化锚；
                        # - 本次 invocation 的全部 unit 共享 compiler_run_ref；
                        # - 非锚 unit 的 content_fingerprint 允许为 NULL；
                        # - fingerprint 查询必须经 compiler_run_ref 解析完整 run 的全部产物。
                        content_fingerprint=fp if seg is segments[0] else None)
                    d = unit.to_row()
                    d["provenance_ref"] = prov.provenance_id
                    self.connection.execute(
                        "INSERT INTO akb_semantic_units (unit_id, evidence_id, unit_type,"
                        " normalized_text, entity_candidates_json, relation_candidates_json,"
                        " temporal_parse_json, ontology_mapping_json, extraction_method,"
                        " extraction_version, provenance_ref, compiler_run_ref,"
                        " configuration_hash, content_fingerprint)"
                        " VALUES (:unit_id, :evidence_id, :unit_type, :normalized_text,"
                        " :entity_candidates_json, :relation_candidates_json,"
                        " :temporal_parse_json, :ontology_mapping_json, :extraction_method,"
                        " :extraction_version, :provenance_ref, :compiler_run_ref,"
                        " :configuration_hash, :content_fingerprint)", d)
                    units.append(unit)
                    if seg is segments[0]:  # 每单证据编译只建一组 assertion（幂等锚在 unit0）
                        built = self.builder.build(
                            unit, actor_id=actor_id, ontology_scope=ontology_scope,
                            quarantined=quarantined)
                        if built:
                            assertions.extend(built)
                except CompilationError as exc:
                    if exc.code in ("E-NORMALIZATION-FAILED",):
                        warnings.append(f"segment {seg.segment_id}: {exc.code}")
                        continue
                    raise
            run.status = "completed"
            run.warnings = warnings
            self.connection.execute(
                "UPDATE akb_compilation_runs SET status=?, warnings_json=?, finished_at=?"
                " WHERE run_id=?", (run.status, canonical_json(warnings), _now(), run.run_id))
            self.connection.execute(f"RELEASE {sp}")
            return CompilationResult(run=run, units=units, assertions=assertions,
                                     warnings=warnings, fingerprint=fp, idempotent_hit=False)
        except Exception:
            self.connection.execute(f"ROLLBACK TO {sp}")
            self.connection.execute(f"RELEASE {sp}")
            # run 失败也留 provenance 痕（append-only 审计；错误不越界）
            self.connection.execute(
                "UPDATE akb_compilation_runs SET status='failed', finished_at=? WHERE run_id=?",
                (_now(), run.run_id))
            raise

    def _assertions_for_units(self, unit_ids: list[str]) -> list[KnowledgeAssertion]:
        out: list[KnowledgeAssertion] = []
        for uid in unit_ids:
            rows = self.connection.execute(
                "SELECT * FROM akb_assertions WHERE source_unit_refs_json LIKE ?",
                (f'%"{uid}"%',)).fetchall()
            out.extend(KnowledgeAssertion.from_row(r) for r in rows)
        return out

    def _unit_from_row(self, row) -> SemanticUnitRecord:
        import json as _j
        return SemanticUnitRecord(
            unit_id=row["unit_id"], evidence_id=row["evidence_id"],
            unit_type=row["unit_type"], normalized_text=row["normalized_text"],
            entity_candidates=_j.loads(row["entity_candidates_json"]),
            relation_candidates=_j.loads(row["relation_candidates_json"]),
            temporal_parse=_j.loads(row["temporal_parse_json"]) if row["temporal_parse_json"] else None,
            ontology_mapping=_j.loads(row["ontology_mapping_json"]) if row["ontology_mapping_json"] else None,
            extraction_method=row["extraction_method"],
            extraction_version=row["extraction_version"],
            provenance_ref=row["provenance_ref"], compiler_run_ref=row["compiler_run_ref"],
            configuration_hash=row["configuration_hash"],
            content_fingerprint=row["content_fingerprint"], created_at=row["created_at"])


def _run_kwargs(row) -> dict:
    import json as _j
    return {"run_id": row["run_id"], "evidence_ids": _j.loads(row["evidence_ids_json"]),
            "compiler_version": row["compiler_version"],
            "configuration_hash": row["configuration_hash"],
            "ontology_version": row["ontology_version"], "provider_id": row["provider_id"],
            "actor_id": row["actor_id"], "policy_version": row["policy_version"],
            "status": row["status"], "warnings": _j.loads(row["warnings_json"]),
            "created_at": row["created_at"], "finished_at": row["finished_at"]}


def _kind_of(actor_id: str) -> str:
    if actor_id.startswith("human:"):
        return "human"
    if actor_id.startswith("llm:"):
        return "llm"
    if actor_id.startswith("agent:"):
        return "agent"
    return "system"


def json_field(row, key: str, index: int):
    import json as _j
    return _j.loads(row[key] or "[]")[index]