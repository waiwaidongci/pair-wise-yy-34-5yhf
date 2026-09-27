import tempfile, unittest
from pathlib import Path
from src.domain import ConflictError, NotFoundError, PermissionDenied, ValidationError
from src.repository import Repository
from src.service import Service
from src.rules import TRANSITION_ROLES


class StatementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(str(Path(self.tmp.name) / "test.db"))
        self.service = Service(self.repo)
        self.item = self.service.create_item(
            {"title": "吊车倾覆事故", "description": "东门吊装区吊车倾覆",
             "severity": "serious", "quantity": 2, "threshold": 5,
             "external_ref": "ST-1"}, "creator", "reporter")

    def tearDown(self):
        self.repo.close()
        self.tmp.cleanup()

    def _submit(self, witness, position, content):
        return self.service.submit_statement(
            self.item["id"],
            {"witness": witness, "position": position, "content": content},
            "investigator-li", "investigator")

    def _review(self, statement_id, verdict, note="已核对"):
        return self.service.review_statement(
            self.item["id"], statement_id, {"verdict": verdict, "note": note},
            "safety-wang", "safety_manager")

    def _reach_corrective(self):
        current = self.service.get_item(self.item["id"], "viewer")
        for target in ("investigating", "corrective_action"):
            current = self.service.transition(
                current["id"], target, current["version"],
                "investigator-li", TRANSITION_ROLES[target][0])
        return current

    def test_register_by_witness_and_position_keeps_new_version(self):
        first = self._submit("张三", "东门", "吊车先向左倾斜")
        self.assertEqual(first["version"], 1)
        second = self._submit("张三", "东门", "吊车先向左倾斜随后倒下")
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["content"], "吊车先向左倾斜随后倒下")
        other_position = self._submit("张三", "西门", "听到巨响")
        self.assertEqual(other_position["version"], 1)
        self.assertNotEqual(other_position["id"], first["id"])
        statements = self.service.list_statements(self.item["id"], "viewer")
        self.assertEqual(len(statements), 2)

    def test_new_version_invalidates_review(self):
        statement = self._submit("李四", "吊装区", "钢索已经断裂")
        reviewed = self._review(statement["id"], "consistent", "与现场照片一致")
        self.assertEqual(reviewed["verdict"], "consistent")
        renewed = self._submit("李四", "吊装区", "钢索先磨损后断裂")
        self.assertEqual(renewed["version"], 2)
        self.assertIsNone(renewed["verdict"])
        self.assertIsNone(renewed["review_note"])
        detail = self.service.get_item(self.item["id"], "viewer")
        pending = detail["statement_summary"]["pending_review"]
        self.assertEqual([p["witness"] for p in pending], ["李四"])
        events = self.service.audit("viewer", self.item["id"])
        submissions = [e for e in events if e["action"] == "statement"]
        self.assertTrue(submissions[-1]["detail"]["review_invalidated"])
        self.assertEqual(submissions[-1]["detail"]["content"], "钢索先磨损后断裂")
        self.assertIn("statement_review", [e["action"] for e in events])
        self.assertTrue(self.repo.verify_audit_chain())

    def test_verification_blocked_by_pending_and_conflict(self):
        current = self._reach_corrective()
        st1 = self._submit("张三", "东门", "看到吊车倾斜")
        st2 = self._submit("王五", "西门", "看到吊臂下有人")
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], "verification",
                                    current["version"], "safety-wang", "safety_manager")
        self._review(st1["id"], "consistent", "与监控一致")
        self._review(st2["id"], "conflict", "与张三说法矛盾")
        detail = self.service.get_item(self.item["id"], "viewer")
        conflicts = detail["statement_summary"]["conflicts"]
        self.assertEqual([c["witness"] for c in conflicts], ["王五"])
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], "verification",
                                    current["version"], "safety-wang", "safety_manager")
        self._review(st2["id"], "consistent", "补充询问后一致")
        done = self.service.transition(current["id"], "verification",
                                       current["version"], "safety-wang", "safety_manager")
        self.assertEqual(done["status"], "verification")

    def test_undetermined_does_not_block_verification(self):
        current = self._reach_corrective()
        statement = self._submit("赵六", "围墙外", "只听到声音")
        self._review(statement["id"], "undetermined", "距离太远无法核对")
        done = self.service.transition(current["id"], "verification",
                                       current["version"], "safety-wang", "safety_manager")
        self.assertEqual(done["status"], "verification")

    def test_permissions_and_validation(self):
        with self.assertRaises(PermissionDenied):
            self.service.submit_statement(
                self.item["id"],
                {"witness": "张三", "position": "东门", "content": "看到吊车倾斜"},
                "safety-wang", "safety_manager")
        statement = self._submit("张三", "东门", "看到吊车倾斜")
        with self.assertRaises(PermissionDenied):
            self.service.review_statement(
                self.item["id"], statement["id"],
                {"verdict": "consistent", "note": "已核对"},
                "investigator-li", "investigator")
        with self.assertRaises(ValidationError):
            self._review(statement["id"], "maybe")
        with self.assertRaises(ValidationError):
            self.service.review_statement(
                self.item["id"], statement["id"],
                {"verdict": "consistent", "note": "  "},
                "safety-wang", "safety_manager")
        with self.assertRaises(NotFoundError):
            self._review(9999, "consistent")
        with self.assertRaises(NotFoundError):
            self.service.submit_statement(
                9999, {"witness": "张三", "position": "东门", "content": "看到吊车倾斜"},
                "investigator-li", "investigator")

    def test_list_and_detail_show_pending_and_conflicts(self):
        self._submit("张三", "东门", "看到吊车倾斜")
        st2 = self._submit("王五", "西门", "看到吊臂下有人")
        self._review(st2["id"], "conflict", "与张三说法矛盾")
        listed = self.service.list_items("viewer")
        summary = listed[0]["statement_summary"]
        self.assertEqual(summary["total"], 2)
        self.assertEqual([p["witness"] for p in summary["pending_review"]], ["张三"])
        self.assertEqual([c["witness"] for c in summary["conflicts"]], ["王五"])


if __name__ == "__main__":
    unittest.main()
