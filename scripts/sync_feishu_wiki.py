#!/usr/bin/env python3
"""Generate the public COOC catalogue from direct children of a Feishu Wiki node."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "site" / "data" / "courses.json"
ORDERED_TITLE = re.compile(r"^(?P<order>\d+)\s*[-_.、:：]\s*(?P<title>.+)$")


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


def public_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname:
        raise RuntimeError("FEISHU_WIKI_BASE_URL must be an https Feishu tenant URL")
    host = parsed.hostname.lower()
    if host != "feishu.cn" and not host.endswith(".feishu.cn"):
        raise RuntimeError("FEISHU_WIKI_BASE_URL must use a feishu.cn host")
    return f"https://{parsed.netloc}"


def title_and_order(value: Any) -> tuple[str, int]:
    title = scalar(value)
    match = ORDERED_TITLE.match(title)
    if not match:
        return title, 999999
    return match.group("title").strip(), int(match.group("order"))


def summary_from_raw_content(value: Any, title: str) -> str:
    content = scalar(value)
    if not content:
        return ""
    for line in content.splitlines():
        line = line.strip().lstrip("#").strip()
        if not line:
            continue
        normalized_line, _ = title_and_order(line)
        if normalized_line == title:
            continue
        return line[:240]
    return ""


def normalize_nodes(nodes: list[dict[str, Any]], raw_content: dict[str, str], base_url: str, generated_at: str) -> dict[str, Any]:
    courses: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("obj_type") != "docx":
            continue
        node_token = scalar(node.get("node_token"))
        document_id = scalar(node.get("obj_token"))
        title, sort_order = title_and_order(node.get("title"))
        if not node_token or not document_id or not title:
            continue
        courses.append(
            {
                "id": node_token,
                "title": title,
                "summary": summary_from_raw_content(raw_content.get(document_id), title),
                "category": "公开课程",
                "document_url": f"{base_url}/wiki/{quote(node_token)}",
                "cover_url": "",
                "updated_at": "",
                "sort_order": sort_order,
            }
        )
    courses.sort(key=lambda item: (item["sort_order"], item["title"]))
    return {"schema_version": 1, "generated_at": generated_at, "courses": courses}


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


def raw_document_content(document_id: str, token: str) -> str:
    data = request_json(
        f"https://open.feishu.cn/open-apis/docx/v1/documents/{quote(document_id)}/raw_content",
        token=token,
    ).get("data", {})
    return scalar(data.get("content"))


def fetch_public_catalogue(base_url: str) -> dict[str, Any]:
    token = tenant_access_token()
    root_token = required_env("FEISHU_WIKI_PUBLIC_ROOT_TOKEN")
    root = resolve_wiki_node(root_token, token)
    nodes = list_direct_children(scalar(root["space_id"]), root_token, token)
    raw_content = {
        scalar(node["obj_token"]): raw_document_content(scalar(node["obj_token"]), token)
        for node in nodes
        if node.get("obj_type") == "docx" and scalar(node.get("obj_token"))
    }
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return normalize_nodes(nodes, raw_content, base_url, generated_at)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync public COOC catalogue from a Feishu Wiki directory.")
    parser.add_argument("--input", type=Path, help="offline fixture with nodes and raw_content fields")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="generated public JSON path")
    parser.add_argument("--generated-at", help="RFC 3339 timestamp for deterministic offline output")
    parser.add_argument("--base-url", help="Feishu tenant URL for offline verification")
    args = parser.parse_args()

    generated_at = args.generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if args.input:
        fixture = json.loads(args.input.read_text(encoding="utf-8"))
        nodes = fixture.get("nodes", [])
        if not isinstance(nodes, list):
            raise ValueError("fixture must contain a nodes array")
        raw_content = fixture.get("raw_content", {})
        if not isinstance(raw_content, dict):
            raise ValueError("fixture raw_content must be an object")
        base_url = public_base_url(args.base_url or "")
        payload = normalize_nodes(nodes, raw_content, base_url, generated_at)
    else:
        payload = fetch_public_catalogue(public_base_url(required_env("FEISHU_WIKI_BASE_URL")))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"published_courses={len(payload['courses'])} output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
