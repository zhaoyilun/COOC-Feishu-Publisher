import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_feishu_wiki import (
    fixture_source,
    list_direct_children,
    list_document_blocks,
    publish_static_site,
    render_inline,
    resolve_wiki_node,
)


class WikiPublisherTests(unittest.TestCase):
    def publish_fixture(self, directory: Path):
        nodes, documents, downloader = fixture_source(ROOT / "samples" / "feishu-wiki-nodes.json")
        return publish_static_site(
            nodes,
            documents,
            downloader,
            directory / "data" / "courses.json",
            directory / "courses",
            "2026-08-05T00:00:00Z",
        )

    def test_public_docx_becomes_a_local_course_page_with_local_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.publish_fixture(root)
            course = payload["courses"][0]
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(course["title"], "示例公开课程")
            self.assertEqual(course["summary"], "这是一门由飞书知识库维护、由 GitHub Pages 完整公开访问的示例课程。")
            self.assertNotIn("node", course["id"])
            self.assertNotIn("document_url", course)

            page = (root / course["course_url"] / "index.html").read_text(encoding="utf-8")
            self.assertIn("课程示意图", page)
            self.assertIn("课程讲义.txt", page)
            self.assertIn('src="assets/', page)
            self.assertIn('href="assets/', page)
            self.assertNotIn("feishu.cn", page)
            self.assertEqual(len(list((root / course["course_url"] / "assets").iterdir())), 2)

    def test_withdrawing_all_courses_removes_old_static_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.publish_fixture(root)
            payload = publish_static_site(
                [],
                {},
                lambda _: self.fail("a withdrawn course must not download media"),
                root / "data" / "courses.json",
                root / "courses",
                "2026-08-05T01:00:00Z",
            )
            self.assertEqual(payload["courses"], [])
            self.assertEqual(list((root / "courses").iterdir()), [])

    def test_feishu_links_are_rendered_as_plain_text_but_external_links_remain_links(self):
        markup = render_inline(
            [
                {"text_run": {"content": "飞书资料", "text_element_style": {"link": {"url": "https://tenant.feishu.cn/docx/secret"}}}},
                {"text_run": {"content": "外部来源", "text_element_style": {"link": {"url": "https://example.com/source"}}}},
            ]
        )
        self.assertNotIn("feishu.cn", markup)
        self.assertIn("飞书资料", markup)
        self.assertIn('href="https://example.com/source"', markup)

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

    def test_document_blocks_are_paginated(self):
        with patch(
            "sync_feishu_wiki.request_json",
            side_effect=[
                {"data": {"items": [{"block_id": "one"}], "has_more": True, "page_token": "next"}},
                {"data": {"items": [{"block_id": "two"}], "has_more": False}},
            ],
        ) as request:
            blocks = list_document_blocks("document", "tenant-token")
        self.assertEqual([block["block_id"] for block in blocks], ["one", "two"])
        self.assertIn("page_size=500", request.call_args_list[0].args[0])
        self.assertIn("page_token=next", request.call_args_list[1].args[0])

    def test_fixture_shape_is_json_serializable(self):
        fixture = json.loads((ROOT / "samples" / "feishu-wiki-nodes.json").read_text(encoding="utf-8"))
        self.assertIn("documents", fixture)
        self.assertIn("media", fixture)


if __name__ == "__main__":
    unittest.main()
