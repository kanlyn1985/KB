"""Phase 5: Requirement graph fusion tests."""
from __future__ import annotations

import tempfile, unittest, shutil
from pathlib import Path
from contextlib import closing

from enterprise_agent_kb.requirements.seed import seed_sample_data
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.graph_fusion import RequirementGraphFusion, ALL_FUSION_RELATIONS


class GraphFusionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        # Create graph_edges table (KB1 table, not in requirement schema)
        with closing(self.repo.connection()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    src_entity_id TEXT,
                    relation TEXT,
                    dst_entity_id TEXT,
                    version_scope TEXT,
                    condition_scope TEXT,
                    confidence REAL,
                    edge_status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
        self.fusion = RequirementGraphFusion(self.repo)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_project_all_returns_five_relation_types(self):
        result = self.fusion.project_all()
        self.assertIn("fusion_relations", result)
        for rel in ALL_FUSION_RELATIONS:
            self.assertIn(rel, result["fusion_relations"])

    def test_verified_by_projects_from_test_results(self):
        result = self.fusion.project_all()
        # seed_sample_data inserts 4 test results
        self.assertGreater(result["fusion_relations"]["verified_by"]["edges_upserted"], 0)

    def test_fusion_edges_use_reqedge_prefix(self):
        self.fusion.project_all()
        listing = self.fusion.list_fusion_edges()
        for edge in listing["edges"]:
            self.assertTrue(edge["edge_id"].startswith("REQEDGE-"))

    def test_idempotent_re_run_does_not_duplicate(self):
        self.fusion.project_all()
        listing1 = self.fusion.list_fusion_edges()
        self.fusion.project_all()
        listing2 = self.fusion.list_fusion_edges()
        self.assertEqual(listing1["fusion_edge_count"], listing2["fusion_edge_count"])

    def test_list_fusion_edges_filters_by_relation(self):
        self.fusion.project_all()
        listing = self.fusion.list_fusion_edges(relation="verified_by")
        for edge in listing["edges"]:
            self.assertEqual(edge["relation"], "verified_by")

    def test_project_all_without_graph_edges_table_returns_zero(self):
        """Standalone requirement workspace without KB1 graph_edges table."""
        tmpdir = tempfile.mkdtemp()
        try:
            root = Path(tmpdir) / "knowledge_base"
            seed_sample_data(root)
            repo = RequirementRepository(root)
            fusion = RequirementGraphFusion(repo)
            result = fusion.project_all()
            # verified_by counts rows scanned but cannot upsert without graph_edges
            listing = fusion.list_fusion_edges()
            self.assertEqual(listing["fusion_edge_count"], 0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
