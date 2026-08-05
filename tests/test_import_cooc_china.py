import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_cooc_china import document_blocks, fetch_local_courses, parse_course


class CoocChinaImportTests(unittest.TestCase):
    def test_parses_front_matter_links_lists_and_cover(self):
        source = """---
title:  "示例 Android 课程"
date: 2024-05-20 00:02:36 +0800
categories: ['Android', '实验']
---
### 课程简介
这是一段课程简介。

* 学习目标一
* 学习目标二

[学习课程](https://example.com/course/)

[![课程封面](/images/book-thumb/course.png)](https://example.com/course/)
"""
        course = parse_course("2024-05-20-course.md", source, {})
        self.assertEqual(course.title, "示例 Android 课程")
        self.assertEqual(course.category, "Android / 实验")
        self.assertEqual(course.published_at, "2024-05-20")
        self.assertEqual(course.course_url, "https://example.com/course/")
        self.assertEqual(course.cover_url, "https://raw.githubusercontent.com/COOC-China/cooc-china.github.io/master/images/book-thumb/course.png")
        self.assertEqual([block.kind for block in course.blocks], ["heading3", "text", "bullet", "bullet", "text"])
        self.assertEqual(course.blocks[-1].href, "https://example.com/course/")

    def test_legacy_post_without_front_matter_gets_stable_title(self):
        source = """### 课程简介
这是一门课程。

[学习课程](https://example.com/legacy/)
"""
        course = parse_course("2019-6-12-Information-Technology-Foundation", source, {})
        self.assertEqual(course.title, "信息技术基础")
        self.assertEqual(course.category, "课程建立")
        self.assertEqual(course.course_url, "https://example.com/legacy/")

    def test_document_blocks_include_editor_metadata_and_image_placeholder(self):
        source = """---
title: "课程 A"
date: 2024-01-02
categories: '教程'
---
### 课程简介
正文。
[学习课程](https://example.com/a/)
![封面](/images/a.png)
"""
        course = parse_course("course-a.md", source, {})
        blocks = document_blocks(course)
        self.assertEqual(blocks[0]["heading1"]["elements"][0]["text_run"]["content"], "课程 A")
        self.assertEqual(blocks[1]["text"]["elements"][0]["text_run"]["content"], "课程分类：教程")
        self.assertEqual(blocks[2]["text"]["elements"][0]["text_run"]["content"], "原始发布日期：2024-01-02")
        self.assertEqual(blocks[-1]["block_type"], 27)

    def test_local_source_directory_is_sorted_by_publish_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "posts"
            directory.mkdir()
            (directory / "old.md").write_text("---\ntitle: 旧课程\ndate: 2020-01-01\n---\n[学习课程](https://example.com/old/)\n", encoding="utf-8")
            (directory / "new.md").write_text("---\ntitle: 新课程\ndate: 2025-01-01\n---\n[学习课程](https://example.com/new/)\n", encoding="utf-8")
            courses = fetch_local_courses(directory)
        self.assertEqual([course.title for course in courses], ["新课程", "旧课程"])


if __name__ == "__main__":
    unittest.main()
