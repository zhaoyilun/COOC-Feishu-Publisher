import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_feishu_bitable import normalize_records, resolve_bitable_app_token


class NormalizeRecordsTests(unittest.TestCase):
    def test_only_published_records_with_titles_are_emitted(self):
        payload = normalize_records(
            [
                {"record_id": "public", "fields": {"课程标题": "公开课程", "公开发布": True, "排序": 2}},
                {"record_id": "private", "fields": {"课程标题": "内部课程", "公开发布": False, "排序": 1}},
                {"record_id": "untitled", "fields": {"公开发布": True}},
            ],
            "2026-08-04T00:00:00Z",
        )
        self.assertEqual([item["id"] for item in payload["courses"]], ["public"])

    def test_public_document_link_must_be_https_feishu_url(self):
        payload = normalize_records(
            [
                {
                    "record_id": "course",
                    "fields": {
                        "课程标题": "课程",
                        "公开发布": "是",
                        "飞书公开文档链接": "https://example.com/private",
                        "封面公开链接": "http://example.com/cover.png",
                    },
                }
            ],
            "2026-08-04T00:00:00Z",
        )
        self.assertEqual(payload["courses"][0]["document_url"], "")
        self.assertEqual(payload["courses"][0]["cover_url"], "")

    def test_courses_sort_by_order_then_title(self):
        payload = normalize_records(
            [
                {"record_id": "b", "fields": {"课程标题": "B", "公开发布": 1, "排序": 10}},
                {"record_id": "a", "fields": {"课程标题": "A", "公开发布": 1, "排序": 10}},
                {"record_id": "first", "fields": {"课程标题": "First", "公开发布": 1, "排序": 1}},
            ],
            "2026-08-04T00:00:00Z",
        )
        self.assertEqual([item["id"] for item in payload["courses"]], ["first", "a", "b"])

    def test_wiki_node_resolves_its_bitable_app_token(self):
        with patch(
            "sync_feishu_bitable.request_json",
            return_value={"data": {"node": {"obj_type": "bitable", "obj_token": "app_token"}}},
        ) as request:
            app_token = resolve_bitable_app_token("wiki_node", "tenant_token")
        self.assertEqual(app_token, "app_token")
        self.assertIn("token=wiki_node", request.call_args.args[0])

    def test_wiki_node_must_reference_a_bitable(self):
        with patch(
            "sync_feishu_bitable.request_json",
            return_value={"data": {"node": {"obj_type": "docx", "obj_token": "document_token"}}},
        ):
            with self.assertRaisesRegex(RuntimeError, "does not reference a Bitable"):
                resolve_bitable_app_token("wiki_node", "tenant_token")

    def test_text_publish_markers_from_the_test_base_are_filtered(self):
        payload = normalize_records(
            [
                {"record_id": "public", "fields": {"课程标题": "公开课程", "公开发布": "true"}},
                {"record_id": "private", "fields": {"课程标题": "内部课程", "公开发布": "false"}},
            ],
            "2026-08-04T00:00:00Z",
        )
        self.assertEqual([item["id"] for item in payload["courses"]], ["public"])


if __name__ == "__main__":
    unittest.main()
