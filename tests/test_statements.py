import tempfile
import unittest
from pathlib import Path

from src.domain import ConflictError, PermissionDenied, ValidationError
from src.repository import Repository
from src.service import Service
from src.rules import STATES, TRANSITION_ROLES


class StatementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(str(Path(self.tmp.name) / "test.db"))
        self.service = Service(self.repo)
        self.item = self.service.create_item(
            {"title": "machine injury", "description": "scene statements",
             "severity": "serious", "quantity": 5, "threshold": 10,
             "external_ref": "ST-1"}, "creator", "reporter")

    def tearDown(self):
        self.repo.close()
        self.tmp.cleanup()

    def _to_corrective_action(self):
        current = self.service.get_item(self.item["id"], "viewer")
        for target in STATES[1:3]:
            current = self.service.transition(
                current["id"], target, current["version"], "reviewer",
                TRANSITION_ROLES[target][0])
        return current

    def test_register_and_resubmit_keeps_new_version(self):
        first = self.service.add_statement(
            self.item["id"],
            {"witness_name": "张三", "position": "车间东门",
             "content": "看到机器未停机"}, "investigator1", "investigator")
        self.assertEqual(first["version"], 1)
        self.assertTrue(first["is_current"])
        second = self.service.add_statement(
            self.item["id"],
            {"witness_name": "张三", "position": "车间东门",
             "content": "补充：当时安全门是开着的"}, "investigator1", "investigator")
        self.assertEqual(second["version"], 2)
        statements = self.service.list_statements(self.item["id"], "viewer")
        self.assertEqual(len(statements), 2)
        old = [s for s in statements if s["id"] == first["id"]][0]
        self.assertFalse(old["is_current"])
        # 不同观察位置分别登记，互不影响
        other = self.service.add_statement(
            self.item["id"],
            {"witness_name": "张三", "position": "办公室窗口",
             "content": "听到异响"}, "investigator1", "investigator")
        self.assertEqual(other["version"], 1)

    def test_review_and_supplement_invalidates_review(self):
        statement = self.service.add_statement(
            self.item["id"],
            {"witness_name": "李四", "position": "流水线旁",
             "content": "看到伤者自己操作"}, "investigator1", "investigator")
        review = self.service.review_statement(
            self.item["id"], statement["id"],
            {"verdict": "consistent", "note": "与监控一致"}, "safety1", "safety_manager")
        self.assertTrue(review["valid"])
        # 证人补充原话后，相关复核失效，新版本回到待复核
        self.service.add_statement(
            self.item["id"],
            {"witness_name": "李四", "position": "流水线旁",
             "content": "补充：操作前未按规程断电"}, "investigator1", "investigator")
        statements = self.service.list_statements(self.item["id"], "viewer")
        old = [s for s in statements if s["id"] == statement["id"]][0]
        self.assertIsNone(old["review"])
        new = [s for s in statements if s["is_current"]][0]
        self.assertIsNone(new["review"])
        with self.assertRaises(ConflictError):
            self.service.review_statement(
                self.item["id"], statement["id"],
                {"verdict": "consistent", "note": "旧版本"}, "safety1", "safety_manager")

    def test_verification_blocked_until_all_consistent(self):
        current = self._to_corrective_action()
        st_a = self.service.add_statement(
            self.item["id"],
            {"witness_name": "王五", "position": "东门", "content": "甲说"},
            "investigator1", "investigator")
        st_b = self.service.add_statement(
            self.item["id"],
            {"witness_name": "赵六", "position": "西门", "content": "乙说"},
            "investigator1", "investigator")
        # 未复核时不能进入验证
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], "verification",
                                    current["version"], "reviewer", "safety_manager")
        self.service.review_statement(
            self.item["id"], st_a["id"],
            {"verdict": "conflicting", "note": "与伤者自述矛盾"}, "safety1", "safety_manager")
        # 存在冲突陈述时不能进入验证
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], "verification",
                                    current["version"], "reviewer", "safety_manager")
        self.service.review_statement(
            self.item["id"], st_a["id"],
            {"verdict": "consistent", "note": "复核后排除矛盾"}, "safety1", "safety_manager")
        self.service.review_statement(
            self.item["id"], st_b["id"],
            {"verdict": "undeterminable", "note": "缺少旁证"}, "safety1", "safety_manager")
        # 存在无法判断的陈述时仍不能进入验证
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], "verification",
                                    current["version"], "reviewer", "safety_manager")
        self.service.review_statement(
            self.item["id"], st_b["id"],
            {"verdict": "consistent", "note": "补充旁证后一致"}, "safety1", "safety_manager")
        done = self.service.transition(current["id"], "verification",
                                       current["version"], "reviewer", "safety_manager")
        self.assertEqual(done["status"], "verification")

    def test_detail_and_list_show_pending_and_conflicts(self):
        st = self.service.add_statement(
            self.item["id"],
            {"witness_name": "孙七", "position": "仓库", "content": "丙说"},
            "investigator1", "investigator")
        detail = self.service.get_item(self.item["id"], "viewer")
        summary = detail["statement_summary"]
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["pending_witnesses"][0]["witness_name"], "孙七")
        self.service.review_statement(
            self.item["id"], st["id"],
            {"verdict": "conflicting", "note": "两人说法矛盾"}, "safety1", "safety_manager")
        listed = [i for i in self.service.list_items("viewer")
                  if i["id"] == self.item["id"]][0]
        summary = listed["statement_summary"]
        self.assertEqual(summary["pending"], 0)
        self.assertEqual(summary["conflicting"], 1)
        self.assertEqual(summary["conflict_items"][0]["statement_id"], st["id"])

    def test_statement_permissions_and_validation(self):
        with self.assertRaises(PermissionDenied):
            self.service.add_statement(
                self.item["id"],
                {"witness_name": "周八", "position": "门口", "content": "丁说"},
                "reporter1", "reporter")
        st = self.service.add_statement(
            self.item["id"],
            {"witness_name": "周八", "position": "门口", "content": "丁说"},
            "investigator1", "investigator")
        with self.assertRaises(PermissionDenied):
            self.service.review_statement(
                self.item["id"], st["id"],
                {"verdict": "consistent", "note": "越权"}, "investigator1", "investigator")
        with self.assertRaises(ValidationError):
            self.service.review_statement(
                self.item["id"], st["id"],
                {"verdict": "unknown", "note": "非法结论"}, "safety1", "safety_manager")
        with self.assertRaises(ValidationError):
            self.service.review_statement(
                self.item["id"], st["id"],
                {"verdict": "consistent", "note": " "}, "safety1", "safety_manager")


if __name__ == "__main__":
    unittest.main()
