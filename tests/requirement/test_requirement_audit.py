"""Phase 6: Audit log bridge tests."""
from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from contextlib import closing
from enterprise_agent_kb.requirements.seed import seed_sample_data
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.audit import RequirementAuditLogger


class AuditLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        # Create audit_log table (KB1 table)
        with closing(self.repo.connection()) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                event_id TEXT PRIMARY KEY, event_type TEXT, timestamp TEXT, payload_json TEXT)""")
            conn.commit()
        self.logger = RequirementAuditLogger(self.repo)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_log_writes_to_audit_log(self):
        eid = self.logger.log(event_type="test_event", actor="alice", payload={"key": "value"})
        self.assertIsNotNone(eid)
        result = self.logger.list_events()
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["events"][0]["event_type"], "requirement.test_event")
        self.assertEqual(result["events"][0]["payload"]["actor"], "alice")

    def test_log_without_audit_log_table_returns_none(self):
        """Standalone workspace without audit_log table."""
        tmpdir = tempfile.mkdtemp()
        import shutil
        try:
            root = Path(tmpdir) / "knowledge_base"
            seed_sample_data(root)
            repo = RequirementRepository(root)
            logger = RequirementAuditLogger(repo)
            result = logger.log(event_type="test", actor="x")
            self.assertIsNone(result)
            listing = logger.list_events()
            self.assertEqual(listing["event_count"], 0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_log_never_raises(self):
        """Audit logging is best-effort, never raises."""
        # This should not raise even with bad payload
        result = self.logger.log(event_type="test", payload=None)
        self.assertIsNotNone(result)

    def test_list_events_filters_requirement_prefix(self):
        # Insert a non-requirement event
        with closing(self.repo.connection()) as conn:
            conn.execute("INSERT INTO audit_log (event_id, event_type, timestamp, payload_json) VALUES (?, ?, ?, ?)",
                         ("OTHER-001", "system.boot", "2026-01-01", "{}"))
            conn.commit()
        self.logger.log(event_type="my_event", actor="alice")
        result = self.logger.list_events()
        # Should only see requirement.* events
        for e in result["events"]:
            self.assertTrue(e["event_type"].startswith("requirement."))


if __name__ == "__main__":
    unittest.main()
