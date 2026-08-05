import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_embedded_system_book import FULLTEXT_MARKER, chapter_blocks, feishu_blocks, has_external_learning_link, source_from_files


class EmbeddedSystemBookImportTests(unittest.TestCase):
    def test_source_uses_only_existing_summary_chapters_and_local_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "content").mkdir()
            (root / "images").mkdir()
            (root / "SUMMARY.md").write_text("* [简介](README.md)\n* [第一章](/content/one.md)\n* [缺失章节](/content/missing.md)\n", encoding="utf-8")
            (root / "README.md").write_text("课程简介\n====\n\n简介正文。\n", encoding="utf-8")
            (root / "content" / "one.md").write_text("#第一节\n\n![](/images/one.png)\n图 1\n\n* 要点\n", encoding="utf-8")
            (root / "content" / "two.md").write_text("#第二节\n\n补充正文。\n", encoding="utf-8")
            (root / "images" / "one.png").write_bytes(b"image")
            source = source_from_files(root)
        self.assertEqual([chapter.title for chapter in source.chapters], ["简介", "第一章", "第二节"])
        self.assertEqual(source.assets, {"images/one.png": b"image"})
        blocks, images = feishu_blocks(source)
        self.assertEqual(blocks[0]["heading1"]["elements"][0]["text_run"]["content"], FULLTEXT_MARKER)
        self.assertEqual(images, ["images/one.png"])
        self.assertEqual(sum(block["block_type"] == 27 for block in blocks), 1)

    def test_parser_converts_quoted_images_captions_and_headings(self):
        blocks = chapter_blocks("#标题\n\n> ![](/images/a.jpg)\n> 图 1-1 示例\n\n第二段\n续行\n")
        self.assertEqual([(block.kind, block.text, block.asset_path) for block in blocks], [
            ("heading3", "标题", ""),
            ("image", "图 1-1 示例", "images/a.jpg"),
            ("text", "第二段 续行", ""),
        ])

    def test_external_learning_link_is_detected_but_plain_text_is_not(self):
        linked = {"block_id": "block", "block_type": 2, "text": {"elements": [{"text_run": {"content": "学习课程", "text_element_style": {"link": {"url": "https://example.com/"}}}}]}}
        plain = {"block_id": "block", "block_type": 2, "text": {"elements": [{"text_run": {"content": "课程正文已迁入本页，由飞书统一维护。", "text_element_style": {}}}]}}
        self.assertTrue(has_external_learning_link(linked))
        self.assertFalse(has_external_learning_link(plain))


if __name__ == "__main__":
    unittest.main()
