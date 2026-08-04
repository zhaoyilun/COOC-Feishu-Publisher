import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_feishu_wiki import list_direct_children, normalize_nodes, public_base_url, resolve_wiki_node


class WikiCatalogueTests(unittest.TestCase):
    def test_only_direct_docx_children_are_published_in_title_order(self):
        payload = normalize_nodes(
            [
                {"node_token": "second", "obj_token": "doc-2", "obj_type": "docx", "title": "010-第二门课程"},
                {"node_token": "folder", "obj_token": "folder-doc", "obj_type": "docx", "title": "内部资料"},
                {"node_token": "first", "obj_token": "doc-1", "obj_type": "docx", "title": "001-第一门课程"},
                {"node_token": "sheet", "obj_token": "sheet-1", "obj_type": "sheet", "title": "不支持的类型"},
            ],
            {"doc-1": "第一门课程摘要\n其余内容", "doc-2": "第二门课程摘要"},
            "https://tenant.feishu.cn",
            "2026-08-05T00:00:00Z",
        )
        self.assertEqual([course["id"] for course in payload["courses"]], ["first", "second", "folder"])
        self.assertEqual(payload["courses"][0]["title"], "第一门课程")
        self.assertEqual(payload["courses"][0]["summary"], "第一门课程摘要")
        self.assertEqual(payload["courses"][0]["document_url"], "https://tenant.feishu.cn/wiki/first")
        self.assertEqual(payload["courses"][2]["summary"], "")

    def test_non_feishu_base_url_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "feishu.cn"):
            public_base_url("https://example.com")

    def test_wiki_root_must_supply_space_id(self):
        with patch("sync_feishu_wiki.request_json", return_value={"data": {"node": {}}}):
            with self.assertRaisesRegex(RuntimeError, "space_id"):
                resolve_wiki_node("root", "tenant-token")

    def test_wiki_children_are_paginated(self):
        with patch(
            "sync_feishu_wiki.request_json",
            side_effect=[
                {"data": {"items": [{"node_token": "one"}], "has_more": True, "page_token": "next"}},
                {"data": {"items": [{"node_token": "two"}], "has_more": False}},
            ],
        ) as request:
            nodes = list_direct_children("space", "root", "tenant-token")
        self.assertEqual([node["node_token"] for node in nodes], ["one", "two"])
        self.assertIn("parent_node_token=root", request.call_args_list[0].args[0])
        self.assertIn("page_token=next", request.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
