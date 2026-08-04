#!/usr/bin/env python3
"""Generate public COOC catalogue data from Feishu Bitable or a local fixture."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "site" / "data" / "courses.json"
FIELD_TITLE = "课程标题"
FIELD_SUMMARY = "课程摘要"
FIELD_CATEGORY = "分类"
FIELD_PUBLISHED = "公开发布"
FIELD_ORDER = "排序"
FIELD_COVER = "封面公开链接"
FIELD_DOCUMENT = "飞书公开文档链接"
FIELD_UPDATED = "最后更新"


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(part for part in (scalar(item) for item in value) if part)
    if isinstance(value, dict):
        for key in ("text", "name", "link", "url"):
            if key in value:
                return scalar(value[key])
    return ""


def is_published(value: Any) -> bool:
    if value is True:
        return True
    return scalar(value).lower() in {"true", "1", "yes", "是", "已发布", "公开"}


def safe_feishu_url(value: Any) -> str:
    url = scalar(value)
    if not url.startswith("https://"):
        return ""
    host = url.split("/", 3)[2].lower() if len(url.split("/", 3)) >= 3 else ""
    return url if host == "feishu.cn" or host.endswith(".feishu.cn") else ""


def safe_https_url(value: Any) -> str:
    url = scalar(value)
    return url if url.startswith("https://") else ""


def order_value(value: Any) -> int:
    try:
        return int(float(scalar(value)))
    except ValueError:
        return 999999


def normalize_records(records: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    courses: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields", {})
        if not isinstance(fields, dict) or not is_published(fields.get(FIELD_PUBLISHED)):
            continue
        title = scalar(fields.get(FIELD_TITLE))
        if not title:
            continue
        courses.append(
            {
                "id": scalar(record.get("record_id")) or title,
                "title": title,
                "summary": scalar(fields.get(FIELD_SUMMARY)),
                "category": scalar(fields.get(FIELD_CATEGORY)),
                "document_url": safe_feishu_url(fields.get(FIELD_DOCUMENT)),
                "cover_url": safe_https_url(fields.get(FIELD_COVER)),
                "updated_at": scalar(fields.get(FIELD_UPDATED)),
                "sort_order": order_value(fields.get(FIELD_ORDER)),
            }
        )
    courses.sort(key=lambda item: (item["sort_order"], item["title"]))
    return {"schema_version": 1, "generated_at": generated_at, "courses": courses}


def read_fixture(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("items", [])
    if not isinstance(records, list):
        raise ValueError("fixture must contain an items array")
    return records


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


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def resolve_bitable_app_token(wiki_node_token: str, token: str) -> str:
    node = request_json(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node"
        f"?token={quote(wiki_node_token)}",
        token=token,
    ).get("data", {}).get("node", {})
    if node.get("obj_type") != "bitable":
        raise RuntimeError("Wiki node does not reference a Bitable resource")
    app_token = scalar(node.get("obj_token"))
    if not app_token:
        raise RuntimeError("Wiki node response did not include a Bitable app token")
    return app_token


def fetch_feishu_records() -> list[dict[str, Any]]:
    app_id = required_env("FEISHU_APP_ID")
    app_secret = required_env("FEISHU_APP_SECRET")
    table_id = required_env("FEISHU_BITABLE_TABLE_ID")
    auth = request_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        method="POST",
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    token = auth["tenant_access_token"]
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    if not app_token:
        app_token = resolve_bitable_app_token(required_env("FEISHU_WIKI_NODE_TOKEN"), token)
    records: list[dict[str, Any]] = []
    page_token = ""
    while True:
        query = "?page_size=100" + (f"&page_token={quote(page_token)}" if page_token else "")
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}/records{query}"
        page = request_json(url, token=token).get("data", {})
        records.extend(page.get("items", []))
        if not page.get("has_more"):
            return records
        page_token = page.get("page_token", "")
        if not page_token:
            raise RuntimeError("Feishu API reported more pages without a page token")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync public COOC catalogue records from Feishu Bitable.")
    parser.add_argument("--input", type=Path, help="API-shaped fixture JSON for offline verification")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="generated public JSON path")
    parser.add_argument("--generated-at", help="RFC 3339 timestamp for deterministic offline output")
    args = parser.parse_args()
    generated_at = args.generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    records = read_fixture(args.input) if args.input else fetch_feishu_records()
    payload = normalize_records(records, generated_at)
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
