# COOC Feishu Publisher

A serverless COOC catalogue: operators maintain only Feishu Wiki documents, while GitHub Actions periodically regenerates the public static catalogue and deploys GitHub Pages.

## Content flow

```text
Feishu Wiki
├─ 公开课程/              # direct child documents become public course cards
└─ 内部资料/              # never read by the publisher
       -> GitHub Actions (scheduled or manual run)
       -> site/data/courses.json
       -> GitHub Pages
       -> public visitor
```

The public site remains a stable GitHub URL. Each card links to its Feishu document; the long-form course content and attachments stay in Feishu. GitHub Actions is short-lived CI, not an application server.

## Operator workflow

1. Create or edit a course document directly under `公开课程`.
2. Move a course out of `公开课程` to withdraw it from the next static sync.
3. Run **Sync public COOC catalogue from Feishu Wiki** manually, or wait for its daily schedule.

Only direct `docx` children of the configured `公开课程` node are emitted. An optional numeric prefix such as `001-课程名称` controls display order and is omitted from the public title. The first non-empty line of each document is used as the card summary.

## Local verification

```sh
python3 scripts/sync_feishu_wiki.py \
  --input samples/feishu-wiki-nodes.json \
  --base-url https://tenant.feishu.cn
python3 -m unittest discover -s tests -v
python3 -m http.server 4173 -d site
```

## Production configuration

Set application credentials only in GitHub Secrets:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_WIKI_PUBLIC_ROOT_TOKEN` — the `公开课程` Wiki node token

Set `FEISHU_WIKI_BASE_URL` as a GitHub Actions variable, for example `https://your-tenant.feishu.cn`. The Feishu app needs the published `wiki:wiki:readonly` and `docx:document:readonly` scopes and permission to read the selected Wiki space. No Bitable is required for this flow.

## Public-access boundary

GitHub Pages always exposes the generated title and summary. The `阅读资料` link is independently controlled by Feishu: a tenant administrator must make `互联网获得链接的人` available, then the owner enables that scope on each public course document. Keep internal documents under `内部资料` and do not enable an external link for them.
