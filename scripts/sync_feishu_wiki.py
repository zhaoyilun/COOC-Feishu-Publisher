#!/usr/bin/env python3
"""Publish direct Feishu Wiki course documents as a self-contained static site."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "site" / "data" / "courses.json"
DEFAULT_COURSE_DIR = ROOT / "site" / "courses"
ORDERED_TITLE = re.compile(r"^(?P<order>\d+)\s*[-_.、:：]\s*(?P<title>.+)$")
FEISHU_HOST = re.compile(r"(^|\.)feishu\.cn$", re.IGNORECASE)


@dataclass(frozen=True)
class DownloadedMedia:
    content: bytes
    filename: str
    content_type: str


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None, token: str = "") -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            response_payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Feishu API request failed: {error}") from error
    if response_payload.get("code", 0) != 0:
        raise RuntimeError(f"Feishu API error: {response_payload.get('msg', 'unknown error')}")
    return response_payload


def title_and_order(value: Any) -> tuple[str, int]:
    title = scalar(value)
    match = ORDERED_TITLE.match(title)
    if not match:
        return title, 999999
    return match.group("title").strip(), int(match.group("order"))


def course_slug(node_token: str) -> str:
    return f"course-{hashlib.sha256(node_token.encode('utf-8')).hexdigest()[:12]}"


def course_id(node_token: str) -> str:
    return f"course-{hashlib.sha256(node_token.encode('utf-8')).hexdigest()[:16]}"


def block_data(block: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for kind in (
        "page", "text", "heading1", "heading2", "heading3", "heading4", "heading5", "heading6", "heading7", "heading8", "heading9",
        "bullet", "ordered", "code", "quote", "todo", "callout", "image", "file", "divider", "table", "table_cell", "grid", "grid_column",
        "quote_container", "view", "undefined",
    ):
        value = block.get(kind)
        if isinstance(value, dict):
            return kind, value
    return "unknown", {}


def element_text(element: dict[str, Any]) -> str:
    for kind in ("text_run", "mention_user", "mention_doc", "reminder", "equation", "file"):
        value = element.get(kind)
        if not isinstance(value, dict):
            continue
        for name in ("content", "title", "name", "text"):
            text = scalar(value.get(name))
            if text:
                return text
    return ""


def block_plain_text(block: dict[str, Any]) -> str:
    _, data = block_data(block)
    elements = data.get("elements", [])
    if not isinstance(elements, list):
        return ""
    return "".join(element_text(element) for element in elements if isinstance(element, dict)).strip()


def summary_from_blocks(blocks: list[dict[str, Any]], title: str) -> str:
    for block in blocks:
        text = block_plain_text(block)
        if not text:
            continue
        normalized, _ = title_and_order(text.lstrip("#").strip())
        if normalized == title:
            continue
        return text[:240]
    return ""


def is_feishu_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname and FEISHU_HOST.search(parsed.hostname))


def safe_href(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or is_feishu_url(value):
        return ""
    return value


def render_inline(elements: Any) -> str:
    if not isinstance(elements, list):
        return ""
    rendered: list[str] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        text = element_text(element)
        if not text:
            continue
        output = html.escape(text)
        text_run = element.get("text_run")
        style = text_run.get("text_element_style", {}) if isinstance(text_run, dict) else {}
        if not isinstance(style, dict):
            style = {}
        if style.get("inline_code"):
            output = f"<code>{output}</code>"
        if style.get("bold"):
            output = f"<strong>{output}</strong>"
        if style.get("italic"):
            output = f"<em>{output}</em>"
        if style.get("strikethrough"):
            output = f"<s>{output}</s>"
        link = style.get("link", {})
        href = safe_href(scalar(link.get("url")) if isinstance(link, dict) else scalar(link))
        if href:
            output = f'<a href="{html.escape(href, quote=True)}" rel="noopener noreferrer">{output}</a>'
        rendered.append(output)
    return "".join(rendered)


def safe_filename(value: str, content_type: str) -> str:
    name = Path(unquote(value)).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    if not name:
        extension = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ".bin"
        name = f"attachment{extension}"
    return name[:120]


def content_disposition_filename(header: str) -> str:
    if not header:
        return ""
    message = Message()
    message["content-disposition"] = header
    return scalar(message.get_filename())


def download_feishu_media(file_token: str, access_token: str) -> DownloadedMedia:
    request = Request(
        f"https://open.feishu.cn/open-apis/drive/v1/medias/{quote(file_token)}/download",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            content = response.read()
            content_type = response.headers.get_content_type()
            filename = content_disposition_filename(response.headers.get("Content-Disposition", ""))
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Feishu media download failed: {error}") from error
    if not content:
        raise RuntimeError("Feishu media download returned an empty file")
    return DownloadedMedia(content=content, filename=filename, content_type=content_type)


def fixture_media_downloader(media: dict[str, Any]) -> Callable[[str], DownloadedMedia]:
    def download(file_token: str) -> DownloadedMedia:
        source = media.get(file_token)
        if not isinstance(source, dict):
            raise RuntimeError(f"fixture is missing media token: {file_token}")
        encoded = scalar(source.get("content_base64"))
        if not encoded:
            raise RuntimeError(f"fixture media has no content: {file_token}")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise RuntimeError(f"fixture media is not valid base64: {file_token}") from error
        return DownloadedMedia(
            content=content,
            filename=scalar(source.get("filename")),
            content_type=scalar(source.get("content_type")) or "application/octet-stream",
        )

    return download


class StaticCourseRenderer:
    def __init__(self, blocks: list[dict[str, Any]], title: str, course_dir: Path, media_downloader: Callable[[str], DownloadedMedia]):
        self.blocks = {scalar(block.get("block_id")): block for block in blocks if isinstance(block, dict) and scalar(block.get("block_id"))}
        self.title = title
        self.course_dir = course_dir
        self.media_downloader = media_downloader
        self.media_paths: dict[str, str] = {}
        self.seen: set[str] = set()
        self.skipped_title = False

    def media_path(self, file_token: str) -> str:
        cached = self.media_paths.get(file_token)
        if cached:
            return cached
        media = self.media_downloader(file_token)
        filename = safe_filename(media.filename, media.content_type)
        suffix = Path(filename).suffix or mimetypes.guess_extension(media.content_type) or ".bin"
        local_name = f"{hashlib.sha256(file_token.encode('utf-8')).hexdigest()[:16]}{suffix.lower()}"
        assets_dir = self.course_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / local_name).write_bytes(media.content)
        relative = f"assets/{local_name}"
        self.media_paths[file_token] = relative
        return relative

    def render_document(self, document_id: str) -> str:
        root = self.blocks.get(document_id)
        if root is None:
            root = next((block for block in self.blocks.values() if block.get("block_type") == 1), None)
        if root is None:
            raise RuntimeError("document blocks did not include a page root")
        return self.render_children(root.get("children", []), 0)

    def render_children(self, child_ids: Any, depth: int) -> str:
        if not isinstance(child_ids, list):
            return ""
        return "".join(self.render_block(scalar(child_id), depth) for child_id in child_ids if scalar(child_id))

    def render_block(self, block_id: str, depth: int) -> str:
        if block_id in self.seen:
            return ""
        self.seen.add(block_id)
        block = self.blocks.get(block_id)
        if block is None:
            raise RuntimeError("document block tree referenced a missing block")
        kind, data = block_data(block)
        children = self.render_children(block.get("children", []), depth + 1)
        inline = render_inline(data.get("elements", []))

        if kind.startswith("heading"):
            level = int(kind.removeprefix("heading"))
            plain = block_plain_text(block)
            if not self.skipped_title and title_and_order(plain)[0] == self.title:
                self.skipped_title = True
                return children
            return f"<h{level}>{inline}</h{level}>{children}"
        if kind in {"text", "page"}:
            paragraph = f"<p>{inline}</p>" if inline else ""
            return paragraph + children
        if kind == "bullet":
            return f'<div class="course-list-item" style="--depth:{min(depth, 6)}">• {inline}</div>{children}'
        if kind == "ordered":
            return f'<div class="course-list-item" style="--depth:{min(depth, 6)}">{inline}</div>{children}'
        if kind == "todo":
            checked = "✓" if data.get("style", {}).get("done") else "□"
            return f'<p class="course-todo">{checked} {inline}</p>{children}'
        if kind == "code":
            return f"<pre><code>{inline}</code></pre>{children}"
        if kind == "quote":
            return f"<blockquote>{inline}</blockquote>{children}"
        if kind == "callout":
            return f'<aside class="course-callout">{inline}{children}</aside>'
        if kind == "divider":
            return "<hr>" + children
        if kind == "image":
            file_token = scalar(data.get("token"))
            if not file_token:
                raise RuntimeError("image block did not include a media token")
            path = self.media_path(file_token)
            caption = html.escape(scalar(data.get("caption")))
            return f'<figure><img src="{path}" alt="{caption or "课程图片"}">{f"<figcaption>{caption}</figcaption>" if caption else ""}</figure>{children}'
        if kind == "file":
            file_token = scalar(data.get("token"))
            if not file_token:
                raise RuntimeError("file block did not include a media token")
            path = self.media_path(file_token)
            name = html.escape(scalar(data.get("name")) or "下载附件")
            return f'<p><a class="course-download" href="{path}" download>{name}</a></p>{children}'
        if kind in {"table", "table_cell", "grid", "grid_column", "quote_container", "view", "undefined"}:
            return f'<div class="course-container">{inline}{children}</div>'
        if children:
            return f'<div class="course-container">{children}</div>'
        raise RuntimeError(f"unsupported Feishu block type: {block.get('block_type', 'unknown')}")


def course_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta name=\"description\" content=\"{html.escape(title, quote=True)} - COOC 公开课程\">
  <title>{html.escape(title)} · COOC</title>
  <link rel=\"stylesheet\" href=\"../../styles.css\">
</head>
<body>
  <header class=\"course-hero\">
    <nav class=\"nav\" aria-label=\"主导航\"><a class=\"brand\" href=\"../../\">COOC</a><a class=\"back-link\" href=\"../../\">返回课程目录</a></nav>
  </header>
  <main class=\"course-main\">
    <p class=\"eyebrow dark\">公开课程</p>
    <h1 class=\"course-title\">{html.escape(title)}</h1>
    <article class=\"course-content\">{body or '<p>课程正文正在整理。</p>'}</article>
  </main>
  <footer><span>COOC · 由飞书知识库自动同步至 GitHub Pages</span></footer>
</body>
</html>
"""


def publish_static_site(
    nodes: list[dict[str, Any]],
    document_blocks: dict[str, list[dict[str, Any]]],
    media_downloader: Callable[[str], DownloadedMedia],
    output: Path,
    course_dir: Path,
    generated_at: str,
) -> dict[str, Any]:
    candidates: list[tuple[str, str, str, int]] = []
    for node in nodes:
        if node.get("obj_type") != "docx":
            continue
        node_token = scalar(node.get("node_token"))
        document_id = scalar(node.get("obj_token"))
        title, sort_order = title_and_order(node.get("title"))
        if node_token and document_id and title:
            candidates.append((node_token, document_id, title, sort_order))
    candidates.sort(key=lambda item: (item[3], item[2], item[0]))

    staging = course_dir.with_name(f".{course_dir.name}.staging")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    courses: list[dict[str, Any]] = []
    for node_token, document_id, title, sort_order in candidates:
        blocks = document_blocks.get(document_id)
        if not isinstance(blocks, list):
            raise RuntimeError("document blocks were missing from the publication source")
        slug = course_slug(node_token)
        target = staging / slug
        target.mkdir(parents=True, exist_ok=True)
        renderer = StaticCourseRenderer(blocks, title, target, media_downloader)
        body = renderer.render_document(document_id)
        (target / "index.html").write_text(course_page(title, body), encoding="utf-8")
        courses.append(
            {
                "id": course_id(node_token),
                "title": title,
                "summary": summary_from_blocks(blocks, title),
                "category": "公开课程",
                "course_url": f"courses/{slug}/",
                "updated_at": "",
                "sort_order": sort_order,
            }
        )

    shutil.rmtree(course_dir, ignore_errors=True)
    staging.replace(course_dir)
    payload = {"schema_version": 2, "generated_at": generated_at, "courses": courses}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def tenant_access_token() -> str:
    auth = request_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        method="POST",
        payload={"app_id": required_env("FEISHU_APP_ID"), "app_secret": required_env("FEISHU_APP_SECRET")},
    )
    token = scalar(auth.get("tenant_access_token"))
    if not token:
        raise RuntimeError("Feishu tenant access-token response did not include a token")
    return token


def resolve_wiki_node(node_token: str, token: str) -> dict[str, Any]:
    node = request_json(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node"
        f"?token={quote(node_token)}",
        token=token,
    ).get("data", {}).get("node", {})
    if not isinstance(node, dict) or not scalar(node.get("space_id")):
        raise RuntimeError("Wiki root node response did not include a space_id")
    return node


def list_direct_children(space_id: str, parent_node_token: str, token: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    page_token = ""
    while True:
        query = f"?parent_node_token={quote(parent_node_token)}&page_size=50"
        if page_token:
            query += f"&page_token={quote(page_token)}"
        page = request_json(
            f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{quote(space_id)}/nodes{query}",
            token=token,
        ).get("data", {})
        items = page.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("Wiki list response did not include an items array")
        nodes.extend(item for item in items if isinstance(item, dict))
        if not page.get("has_more"):
            return nodes
        page_token = scalar(page.get("page_token"))
        if not page_token:
            raise RuntimeError("Feishu API reported more Wiki nodes without a page token")


def list_document_blocks(document_id: str, token: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    page_token = ""
    while True:
        query = "?page_size=500&document_revision_id=-1"
        if page_token:
            query += f"&page_token={quote(page_token)}"
        page = request_json(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{quote(document_id)}/blocks{query}",
            token=token,
        ).get("data", {})
        items = page.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("document blocks response did not include an items array")
        blocks.extend(item for item in items if isinstance(item, dict))
        if not page.get("has_more"):
            return blocks
        page_token = scalar(page.get("page_token"))
        if not page_token:
            raise RuntimeError("Feishu API reported more document blocks without a page token")


def fetch_production_source() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], Callable[[str], DownloadedMedia]]:
    token = tenant_access_token()
    root_token = required_env("FEISHU_WIKI_PUBLIC_ROOT_TOKEN")
    root = resolve_wiki_node(root_token, token)
    nodes = list_direct_children(scalar(root["space_id"]), root_token, token)
    document_blocks = {
        scalar(node["obj_token"]): list_document_blocks(scalar(node["obj_token"]), token)
        for node in nodes
        if node.get("obj_type") == "docx" and scalar(node.get("obj_token"))
    }
    return nodes, document_blocks, lambda file_token: download_feishu_media(file_token, token)


def fixture_source(path: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], Callable[[str], DownloadedMedia]]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    nodes = fixture.get("nodes", [])
    documents = fixture.get("documents", {})
    media = fixture.get("media", {})
    if not isinstance(nodes, list) or not isinstance(documents, dict) or not isinstance(media, dict):
        raise ValueError("fixture must contain nodes, documents, and media objects")
    document_blocks = {
        document_id: value.get("blocks", [])
        for document_id, value in documents.items()
        if isinstance(document_id, str) and isinstance(value, dict)
    }
    if any(not isinstance(blocks, list) for blocks in document_blocks.values()):
        raise ValueError("every fixture document must contain a blocks array")
    return nodes, document_blocks, fixture_media_downloader(media)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish public Feishu Wiki courses as GitHub static pages.")
    parser.add_argument("--input", type=Path, help="offline fixture with nodes, document blocks, and media")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="generated catalogue JSON path")
    parser.add_argument("--course-directory", type=Path, default=DEFAULT_COURSE_DIR, help="generated static course directory")
    parser.add_argument("--generated-at", help="RFC 3339 timestamp for deterministic offline output")
    args = parser.parse_args()

    generated_at = args.generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    source = fixture_source(args.input) if args.input else fetch_production_source()
    payload = publish_static_site(*source, args.output, args.course_directory, generated_at)
    print(f"published_courses={len(payload['courses'])} output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
