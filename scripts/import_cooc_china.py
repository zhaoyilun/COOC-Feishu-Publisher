#!/usr/bin/env python3
"""One-time, idempotent migration of official COOC-China courses into Feishu Wiki."""

from __future__ import annotations

import argparse
import ast
import json
import mimetypes
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from sync_feishu_wiki import (
    list_direct_children,
    request_json,
    resolve_wiki_node,
    required_env,
    scalar,
    tenant_access_token,
    title_and_order,
)

SOURCE_OWNER = "COOC-China"
SOURCE_REPOSITORY = "cooc-china.github.io"
SOURCE_BRANCH = "master"
SOURCE_POSTS_PATH = "_posts"
RAW_BASE = f"https://raw.githubusercontent.com/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/{SOURCE_BRANCH}/"
CONTENTS_API = f"https://api.github.com/repos/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/contents/{SOURCE_POSTS_PATH}?ref={SOURCE_BRANCH}"
EXPECTED_COURSE_COUNT = 20
LEGACY_TITLES = {"2019-6-12-Information-Technology-Foundation": "信息技术基础"}
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
MARKDOWN_LINK = re.compile(r"^\s*\[([^\]]+)\]\(([^)]+)\)\s*$")
YAML_FIELD = re.compile(r"^(?P<key>[A-Za-z_]+):\s*(?P<value>.*)$")
DATE_VALUE = re.compile(r"(?P<value>\d{4}-\d{1,2}-\d{1,2})")
HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
BULLET = re.compile(r"^\s*[*+-]\s+(?P<text>.+?)\s*$")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
GALLERY_ITEM = re.compile(r'<a\s+href=["\'](?P<link>[^"\']+)["\'][^>]*>\s*<img\s+src=["\'](?P<image>[^"\']+)["\']', re.IGNORECASE)


@dataclass(frozen=True)
class ContentBlock:
    kind: str
    text: str = ""
    href: str = ""


@dataclass(frozen=True)
class CourseSource:
    source_path: str
    title: str
    category: str
    published_at: str
    blocks: tuple[ContentBlock, ...]
    course_url: str
    cover_url: str


def encoded_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, quote(parsed.path, safe="/%"), parsed.query, parsed.fragment))


def fetch_bytes(url: str) -> bytes:
    request = Request(encoded_url(url), headers={"Accept": "application/vnd.github+json", "User-Agent": "cooc-feishu-publisher"})
    try:
        with urlopen(request, timeout=60) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"COOC-China source request failed: {error}") from error


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8")


def clean_url(value: str) -> str:
    return value.strip().split(maxsplit=1)[0].strip()


def is_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def source_asset_url(value: str) -> str:
    value = clean_url(value)
    if value.startswith("/"):
        return RAW_BASE + quote(value.lstrip("/"), safe="/")
    if value.startswith(f"https://github.com/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/raw/"):
        return value.replace(f"https://github.com/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/raw/", RAW_BASE, 1)
    if value.startswith(f"https://raw.githubusercontent.com/{SOURCE_OWNER}/{SOURCE_REPOSITORY}/"):
        return value
    return ""


def parse_scalar(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1].strip()
    return value


def parse_categories(value: str) -> str:
    value = value.strip()
    if not value:
        return "课程建立"
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return parse_scalar(value).strip("[]") or "课程建立"
    if isinstance(parsed, list):
        values = [scalar(item) for item in parsed]
        return " / ".join(item for item in values if item) or "课程建立"
    return scalar(parsed) or "课程建立"


def parse_front_matter(source_path: str, text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    closing = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if closing is None:
        return {}, text
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        match = YAML_FIELD.match(line.replace("\u00a0", " "))
        if match:
            fields[match.group("key")] = match.group("value")
    return fields, "\n".join(lines[closing + 1:])


def markdown_image_candidates(text: str) -> Iterable[tuple[str, str]]:
    for alt, raw_url in MARKDOWN_IMAGE.findall(text):
        source_url = source_asset_url(raw_url)
        if source_url:
            yield alt.strip(), source_url


def parse_gallery_covers(index_text: str) -> dict[str, str]:
    covers: dict[str, str] = {}
    for match in GALLERY_ITEM.finditer(index_text):
        course_url = clean_url(match.group("link"))
        cover_url = source_asset_url(match.group("image"))
        if is_https_url(course_url) and cover_url:
            covers.setdefault(course_url, cover_url)
    return covers


def extracted_course_url(text: str) -> str:
    preferred: list[str] = []
    fallback: list[str] = []
    for label, raw_url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
        url = clean_url(raw_url)
        if not is_https_url(url):
            continue
        if "学习课程" in label or "开始实验" in label:
            preferred.append(url)
        else:
            fallback.append(url)
    return (preferred or fallback or [""])[0]


def markdown_blocks(text: str) -> tuple[ContentBlock, ...]:
    blocks: list[ContentBlock] = []
    stripped = HTML_COMMENT.sub("", text)
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        if line in {"<details>", "</details>"}:
            continue
        if line.startswith("<summary>") and line.endswith("</summary>"):
            summary = line.removeprefix("<summary>").removesuffix("</summary>").strip()
            if summary:
                blocks.append(ContentBlock("heading2", summary))
            continue
        if MARKDOWN_IMAGE.search(line):
            continue
        heading = HEADING.match(line)
        if heading:
            level = min(len(heading.group("hashes")), 3)
            blocks.append(ContentBlock(f"heading{level}", heading.group("text")))
            continue
        bullet = BULLET.match(line)
        if bullet:
            blocks.append(ContentBlock("bullet", bullet.group("text")))
            continue
        link = MARKDOWN_LINK.match(line)
        if link:
            url = clean_url(link.group(2))
            if is_https_url(url):
                blocks.append(ContentBlock("text", link.group(1).strip(), url))
                continue
        blocks.append(ContentBlock("text", line))
    return tuple(blocks)


def published_date(value: str) -> str:
    match = DATE_VALUE.search(value)
    if not match:
        return ""
    year, month, day = match.group("value").split("-")
    return f"{year}-{int(month):02d}-{int(day):02d}"


def parse_course(source_path: str, text: str, gallery_covers: dict[str, str]) -> CourseSource:
    metadata, body = parse_front_matter(source_path, text)
    fallback_title = LEGACY_TITLES.get(source_path, source_path.rsplit(".", 1)[0].replace("-", " "))
    title = parse_scalar(metadata.get("title", "")) or fallback_title
    category = parse_categories(metadata.get("categories", ""))
    course_url = extracted_course_url(body)
    cover_url = gallery_covers.get(course_url, "")
    if not cover_url:
        cover_url = next((url for _, url in markdown_image_candidates(HTML_COMMENT.sub("", body))), "")
    return CourseSource(
        source_path=source_path,
        title=title,
        category=category,
        published_at=published_date(metadata.get("date", source_path)),
        blocks=markdown_blocks(body),
        course_url=course_url,
        cover_url=cover_url,
    )


def fetch_remote_courses() -> list[CourseSource]:
    entries = json.loads(fetch_text(CONTENTS_API))
    if not isinstance(entries, list):
        raise RuntimeError("COOC-China post directory response was not a list")
    index_text = fetch_text(RAW_BASE + "index.md")
    gallery_covers = parse_gallery_covers(index_text)
    courses: list[CourseSource] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        source_path = scalar(entry.get("name"))
        download_url = scalar(entry.get("download_url"))
        if not source_path or not download_url:
            continue
        courses.append(parse_course(source_path, fetch_text(download_url), gallery_covers))
    return sorted(courses, key=lambda course: (course.published_at, course.title), reverse=True)


def fetch_local_courses(source_directory: Path) -> list[CourseSource]:
    if not source_directory.is_dir():
        raise ValueError(f"source directory does not exist: {source_directory}")
    index_path = source_directory.parent / "index.md"
    gallery_covers = parse_gallery_covers(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    courses = [parse_course(path.name, path.read_text(encoding="utf-8"), gallery_covers) for path in source_directory.iterdir() if path.is_file()]
    return sorted(courses, key=lambda course: (course.published_at, course.title), reverse=True)


def text_block(kind: str, text: str, href: str = "") -> dict[str, Any]:
    block_types = {"text": 2, "heading1": 3, "heading2": 4, "heading3": 5, "bullet": 12}
    if kind not in block_types:
        raise ValueError(f"unsupported source content block: {kind}")
    style: dict[str, Any] = {}
    if href:
        style["link"] = {"url": href}
    return {
        "block_type": block_types[kind],
        kind: {"elements": [{"text_run": {"content": text, "text_element_style": style}}]},
    }


def document_blocks(course: CourseSource) -> list[dict[str, Any]]:
    blocks = [
        text_block("heading1", course.title),
        text_block("text", f"课程分类：{course.category}"),
        text_block("text", f"原始发布日期：{course.published_at}"),
    ]
    blocks.extend(text_block(block.kind, block.text, block.href) for block in course.blocks)
    if course.cover_url:
        blocks.append({"block_type": 27, "image": {"caption": {"content": f"{course.title} 课程封面"}}})
    return blocks


def create_wiki_document(space_id: str, parent_node_token: str, title: str, token: str) -> dict[str, Any]:
    response = request_json(
        f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{quote(space_id)}/nodes",
        method="POST",
        payload={"obj_type": "docx", "parent_node_token": parent_node_token, "node_type": "origin", "title": title},
        token=token,
    )
    node = response.get("data", {}).get("node", {})
    if not isinstance(node, dict) or not scalar(node.get("obj_token")):
        raise RuntimeError("created Wiki node did not include a docx token")
    return node


def create_document_blocks(document_id: str, blocks: list[dict[str, Any]], token: str) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for start in range(0, len(blocks), 50):
        response = request_json(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{quote(document_id)}/blocks/{quote(document_id)}/children",
            method="POST",
            payload={"children": blocks[start:start + 50]},
            token=token,
        )
        children = response.get("data", {}).get("children", [])
        if not isinstance(children, list) or len(children) != len(blocks[start:start + 50]):
            raise RuntimeError("created document blocks did not match the requested block count")
        created.extend(item for item in children if isinstance(item, dict))
    return created


def multipart_request(url: str, fields: dict[str, str], filename: str, content: bytes, token: str) -> dict[str, Any]:
    boundary = f"----cooc-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ))
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.extend((
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ))
    request = Request(
        url,
        data=b"".join(chunks),
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Feishu media upload failed: {error}") from error
    if payload.get("code", 0) != 0:
        raise RuntimeError(f"Feishu media upload error: {payload.get('msg', 'unknown error')}")
    return payload


def filename_from_url(url: str) -> str:
    name = Path(urlsplit(url).path).name
    return name or "course-cover.png"


def upload_cover(document_id: str, image_block_id: str, image_url: str, token: str) -> None:
    content = fetch_bytes(image_url)
    if not content:
        raise RuntimeError("COOC-China cover image was empty")
    filename = filename_from_url(image_url)
    response = multipart_request(
        "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all",
        {
            "file_name": filename,
            "parent_type": "docx_image",
            "parent_node": image_block_id,
            "size": str(len(content)),
            "extra": json.dumps({"drive_route_token": document_id}),
        },
        filename,
        content,
        token,
    )
    file_token = scalar(response.get("data", {}).get("file_token"))
    if not file_token:
        raise RuntimeError("Feishu media upload did not return a file token")
    request_json(
        f"https://open.feishu.cn/open-apis/docx/v1/documents/{quote(document_id)}/blocks/{quote(image_block_id)}",
        method="PATCH",
        payload={"replace_image": {"token": file_token}},
        token=token,
    )


def migrate_courses(courses: list[CourseSource], dry_run: bool = False) -> tuple[list[str], list[str]]:
    if dry_run:
        return [course.title for course in courses], []
    token = tenant_access_token()
    root_token = required_env("FEISHU_WIKI_PUBLIC_ROOT_TOKEN")
    root = resolve_wiki_node(root_token, token)
    space_id = scalar(root["space_id"])
    existing_nodes = list_direct_children(space_id, root_token, token)
    existing_titles = {title_and_order(node.get("title"))[0] for node in existing_nodes if node.get("obj_type") == "docx"}
    created: list[str] = []
    skipped: list[str] = []
    for course in courses:
        if course.title in existing_titles:
            skipped.append(course.title)
            continue
        node = create_wiki_document(space_id, root_token, course.title, token)
        document_id = scalar(node["obj_token"])
        requested_blocks = document_blocks(course)
        created_blocks = create_document_blocks(document_id, requested_blocks, token)
        if course.cover_url:
            image_index = next(index for index, block in enumerate(requested_blocks) if block["block_type"] == 27)
            image_block_id = scalar(created_blocks[image_index].get("block_id"))
            if not image_block_id:
                raise RuntimeError("created image block did not include a block id")
            upload_cover(document_id, image_block_id, course.cover_url, token)
        created.append(course.title)
    return created, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate official COOC-China courses into the public Feishu Wiki directory.")
    parser.add_argument("--source-directory", type=Path, help="offline directory of source posts for deterministic testing")
    parser.add_argument("--dry-run", action="store_true", help="parse and validate the migration source without changing Feishu")
    parser.add_argument("--expected-count", type=int, default=EXPECTED_COURSE_COUNT, help="required course count before write (default: 20)")
    args = parser.parse_args()

    courses = fetch_local_courses(args.source_directory) if args.source_directory else fetch_remote_courses()
    if len(courses) != args.expected_count:
        raise RuntimeError(f"expected {args.expected_count} COOC-China courses, found {len(courses)}")
    missing = [course.title for course in courses if not course.blocks or not course.course_url]
    if missing:
        raise RuntimeError(f"course source is incomplete: {', '.join(missing)}")
    created, skipped = migrate_courses(courses, dry_run=args.dry_run)
    print(f"source_courses={len(courses)} created={len(created)} skipped_existing={len(skipped)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
