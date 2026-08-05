#!/usr/bin/env python3
"""One-time import of the authorized COOC-China embedded systems book into Feishu."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from import_cooc_china import CoverAsset, create_document_blocks, fetch_bytes, fetch_text, text_block, upload_cover
from sync_feishu_wiki import (
    block_data,
    block_plain_text,
    list_direct_children,
    list_document_blocks,
    request_json,
    resolve_wiki_node,
    required_env,
    scalar,
    tenant_access_token,
    title_and_order,
)

SOURCE_OWNER = "COOC-China"
SOURCE_REPOSITORY = "Embedded-System-Development-Book"
SOURCE_BRANCH = "master"
RAW_BASE = f"https://raw.githubusercontent.com/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/{SOURCE_BRANCH}/"
TREE_API = f"https://api.github.com/repos/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/git/trees/{SOURCE_BRANCH}?recursive=1"
COURSE_TITLE = "嵌入式系统底层开发"
FULLTEXT_MARKER = "课程正文（COOC-China 授权迁移）"
REPLACEMENT_NOTICE = "课程正文已迁入本页，由飞书统一维护。"
CONFIRMATION_VALUE = "IMPORT_COOC_EMBEDDED_SYSTEM_BOOK"

SUMMARY_ENTRY = re.compile(r"^\s*[*+-]\s+\[([^\]]+)\]\(([^)]*)\)\s*$")
ATX_HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
BULLET = re.compile(r"^\s*[*+-]\s+(.+?)\s*$")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
SETEXT = re.compile(r"^\s*(=+|-+)\s*$")


@dataclass(frozen=True)
class BookBlock:
    kind: str
    text: str = ""
    asset_path: str = ""


@dataclass(frozen=True)
class Chapter:
    title: str
    source_path: str
    blocks: tuple[BookBlock, ...]


@dataclass(frozen=True)
class BookSource:
    chapters: tuple[Chapter, ...]
    assets: dict[str, bytes]


def normalized_path(value: str) -> str:
    parts = value.strip().split(maxsplit=1)
    if not parts:
        return ""
    path = parts[0].lstrip("/")
    if not path or path.startswith("../") or "/../" in path:
        return ""
    return path


def summary_entries(text: str, available_paths: set[str]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = SUMMARY_ENTRY.match(line)
        if not match:
            continue
        title, raw_path = match.groups()
        path = normalized_path(raw_path)
        if path and path.endswith(".md") and path in available_paths and path not in seen:
            entries.append((title.strip(), path))
            seen.add(path)
    return entries


def unquoted(line: str) -> str:
    return line.strip().removeprefix("> ").removeprefix(">").strip()


def chapter_blocks(text: str) -> tuple[BookBlock, ...]:
    blocks: list[BookBlock] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(BookBlock("text", " ".join(paragraph)))
            paragraph.clear()

    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = unquoted(lines[index])
        if not line:
            flush_paragraph()
            index += 1
            continue
        if line.lower().startswith("<script"):
            flush_paragraph()
            blocks.append(BookBlock("text", "原始在线演示未迁入；请在飞书中维护本地课件或附件。"))
            index += 1
            continue
        if index + 1 < len(lines) and SETEXT.match(unquoted(lines[index + 1])):
            flush_paragraph()
            marker = unquoted(lines[index + 1])
            blocks.append(BookBlock("heading2" if marker.startswith("=") else "heading3", line))
            index += 2
            continue
        image = IMAGE.search(line)
        if image:
            flush_paragraph()
            caption = image.group(1).strip()
            if index + 1 < len(lines):
                next_line = unquoted(lines[index + 1])
                if next_line.startswith("图"):
                    caption = next_line
                    index += 1
            path = normalized_path(image.group(2))
            if path:
                blocks.append(BookBlock("image", caption, path))
            index += 1
            continue
        heading = ATX_HEADING.match(line)
        if heading:
            flush_paragraph()
            blocks.append(BookBlock("heading3", heading.group(2)))
            index += 1
            continue
        bullet = BULLET.match(line)
        if bullet:
            flush_paragraph()
            blocks.append(BookBlock("bullet", bullet.group(1)))
            index += 1
            continue
        paragraph.append(line)
        index += 1
    flush_paragraph()
    return tuple(blocks)


def source_sort_key(path: str) -> tuple[int, tuple[int, ...], str]:
    if path == "README.md":
        return (0, (), path)
    if path == "content/slide.md":
        return (2, (), path)
    numeric = tuple(int(value) for value in re.findall(r"\d+", Path(path).stem))
    return (1, numeric, path)


def title_from_source(path: str, text: str) -> str:
    lines = text.splitlines()
    for index, raw_line in enumerate(lines):
        line = unquoted(raw_line)
        heading = ATX_HEADING.match(line)
        if heading:
            return heading.group(2)
        if line and index + 1 < len(lines) and SETEXT.match(unquoted(lines[index + 1])):
            return line
    return Path(path).stem


def source_from_content(summary: str, markdown: dict[str, str], assets: dict[str, bytes]) -> BookSource:
    available_paths = set(markdown)
    summary_paths = summary_entries(summary, available_paths)
    if not summary_paths:
        raise RuntimeError("COOC-China book summary did not reference any available Markdown chapters")

    titles = {path: title for title, path in summary_paths}
    ordered_paths = sorted((path for path in available_paths if path != "SUMMARY.md"), key=source_sort_key)
    chapters: list[Chapter] = []
    content_hashes: set[str] = set()
    for path in ordered_paths:
        text = markdown[path]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in content_hashes:
            continue
        content_hashes.add(digest)
        blocks = chapter_blocks(text)
        if not blocks:
            raise RuntimeError(f"COOC-China book contains an empty chapter: {path}")
        chapters.append(Chapter(titles.get(path, title_from_source(path, text)), path, blocks))

    referenced_assets = {block.asset_path for chapter in chapters for block in chapter.blocks if block.asset_path}
    missing = sorted(referenced_assets - assets.keys())
    if missing:
        raise RuntimeError(f"COOC-China book image files are missing: {', '.join(missing)}")
    return BookSource(tuple(chapters), {path: assets[path] for path in referenced_assets})


def source_from_files(root: Path) -> BookSource:
    markdown = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.md")
    }
    if "SUMMARY.md" not in markdown:
        raise RuntimeError("COOC-China book source does not contain SUMMARY.md")
    assets = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".svg"}
    }
    return source_from_content(markdown["SUMMARY.md"], markdown, assets)


def fetch_remote_source() -> BookSource:
    tree = json.loads(fetch_text(TREE_API))
    entries = tree.get("tree", []) if isinstance(tree, dict) else []
    paths = {
        scalar(item.get("path"))
        for item in entries
        if isinstance(item, dict) and item.get("type") == "blob" and scalar(item.get("path"))
    }
    markdown_paths = {path for path in paths if path.endswith(".md")}
    if "SUMMARY.md" not in markdown_paths:
        raise RuntimeError("COOC-China book source does not contain SUMMARY.md")
    markdown = {path: fetch_text(RAW_BASE + quote(path, safe="/")) for path in markdown_paths}
    assets = {
        path: fetch_bytes(RAW_BASE + quote(path, safe="/"))
        for path in paths
        if Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".svg"}
    }
    return source_from_content(markdown["SUMMARY.md"], markdown, assets)


def feishu_blocks(source: BookSource) -> tuple[list[dict[str, Any]], list[str]]:
    blocks: list[dict[str, Any]] = [text_block("heading1", FULLTEXT_MARKER)]
    image_paths: list[str] = []
    for chapter in source.chapters:
        blocks.append(text_block("heading2", chapter.title))
        for block in chapter.blocks:
            if block.kind == "image":
                blocks.append({"block_type": 27, "image": {"caption": {"content": block.text or "课程图片"}}})
                image_paths.append(block.asset_path)
            else:
                blocks.append(text_block(block.kind, block.text))
    return blocks, image_paths


def has_fulltext_marker(blocks: list[dict[str, Any]]) -> bool:
    return any(block_plain_text(block) == FULLTEXT_MARKER for block in blocks)


def has_external_learning_link(block: dict[str, Any]) -> bool:
    if block_plain_text(block) not in {"学习课程", "开始实验"}:
        return False
    _, data = block_data(block)
    elements = data.get("elements", [])
    if not isinstance(elements, list):
        return False
    for element in elements:
        run = element.get("text_run") if isinstance(element, dict) else None
        style = run.get("text_element_style", {}) if isinstance(run, dict) else {}
        link = style.get("link", {}) if isinstance(style, dict) else {}
        if isinstance(link, dict) and urlsplit(scalar(link.get("url"))).scheme in {"http", "https"}:
            return True
    return False


def replace_external_learning_links(document_id: str, blocks: list[dict[str, Any]], token: str) -> int:
    replaced = 0
    for block in blocks:
        if not has_external_learning_link(block):
            continue
        block_id = scalar(block.get("block_id"))
        if not block_id:
            raise RuntimeError("external learning link did not include a block id")
        request_json(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{quote(document_id)}/blocks/{quote(block_id)}",
            method="PATCH",
            payload={"update_text_elements": {"elements": [{"text_run": {"content": REPLACEMENT_NOTICE, "text_element_style": {}}}]}},
            token=token,
        )
        replaced += 1
        time.sleep(0.36)
    return replaced


def create_paced_blocks(document_id: str, blocks: list[dict[str, Any]], token: str) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for start in range(0, len(blocks), 50):
        batch = blocks[start:start + 50]
        created.extend(create_document_blocks(document_id, batch, token))
        if start + len(batch) < len(blocks):
            time.sleep(0.36)
    return created


def migrate_book(source: BookSource, dry_run: bool = False) -> dict[str, int | bool]:
    requested_blocks, image_paths = feishu_blocks(source)
    result: dict[str, int | bool] = {
        "chapters": len(source.chapters),
        "images": len(image_paths),
        "blocks": len(requested_blocks),
        "replaced_external_links": 0,
        "imported": False,
    }
    if dry_run:
        return result

    token = tenant_access_token()
    root_token = required_env("FEISHU_WIKI_PUBLIC_ROOT_TOKEN")
    root = resolve_wiki_node(root_token, token)
    nodes = list_direct_children(scalar(root["space_id"]), root_token, token)
    document_id = next(
        (scalar(node.get("obj_token")) for node in nodes if node.get("obj_type") == "docx" and title_and_order(node.get("title"))[0] == COURSE_TITLE),
        "",
    )
    if not document_id:
        raise RuntimeError(f"public Feishu course document was not found: {COURSE_TITLE}")
    existing_blocks = list_document_blocks(document_id, token)
    if has_fulltext_marker(existing_blocks):
        result["already_imported"] = True
        return result

    result["replaced_external_links"] = replace_external_learning_links(document_id, existing_blocks, token)
    created = create_paced_blocks(document_id, requested_blocks, token)
    if len(created) != len(requested_blocks):
        raise RuntimeError("created Feishu blocks did not match the requested full-text import")
    image_block_ids = [scalar(block.get("block_id")) for block, requested in zip(created, requested_blocks) if requested.get("block_type") == 27]
    if len(image_block_ids) != len(image_paths) or not all(image_block_ids):
        raise RuntimeError("created Feishu image blocks did not match the source images")
    for image_path, image_block_id in zip(image_paths, image_block_ids):
        upload_cover(document_id, image_block_id, CoverAsset(Path(image_path).name, source.assets[image_path]), token)
        time.sleep(0.36)
    result["imported"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the authorized COOC-China embedded systems book into its Feishu course document.")
    parser.add_argument("--source-directory", type=Path, help="offline source directory for deterministic tests")
    parser.add_argument("--dry-run", action="store_true", help="parse and validate the source without writing Feishu")
    parser.add_argument("--confirm", help=f"required confirmation value: {CONFIRMATION_VALUE}")
    args = parser.parse_args()
    source = source_from_files(args.source_directory) if args.source_directory else fetch_remote_source()
    if not args.dry_run and args.confirm != CONFIRMATION_VALUE:
        raise RuntimeError(f"pass --confirm {CONFIRMATION_VALUE} to write the authorized course into Feishu")
    result = migrate_book(source, dry_run=args.dry_run)
    print(" ".join(f"{name}={value}" for name, value in result.items()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
