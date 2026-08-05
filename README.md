# COOC Feishu Publisher

A serverless static publisher: course editors maintain Feishu Wiki; learners visit only GitHub Pages. GitHub Actions reads the selected public Wiki directory, renders each document as a static course page, downloads its images and attachments, and deploys the result. No application server or visitor Feishu account is required.

## Content flow

```text
Feishu Wiki (editing source)
├─ 公开课程/              # direct child documents are published
└─ 内部资料/              # never read by the publisher
       ↓ GitHub Actions (scheduled or manual)
       ↓ site/courses/<stable-course-id>/index.html + assets/
       ↓ site/data/courses.json
       ↓ GitHub Pages (the only learner-facing entry)
```

Generated course pages do not contain Feishu document links. Moving a document out of `公开课程` removes its generated page and assets at the next successful sync.

## Editor workflow

1. Create or edit one course document directly under `公开课程`.
2. Put images and downloadable files directly in that document.
3. Run **Publish complete COOC courses from Feishu Wiki** manually, or wait for the daily schedule.
4. Visit GitHub Pages to review the complete public result. To withdraw a course, move it into `内部资料` and run the sync again.

An optional prefix such as `001-课程名称` controls ordering only. Document titles, paragraphs, headings, lists, code, quotations, callouts, images, files, and supported containers are emitted as static content. A new unsupported leaf Block fails the sync so public pages are never silently incomplete.

## Local verification

```sh
python3 scripts/sync_feishu_wiki.py --input samples/feishu-wiki-nodes.json
python3 -m unittest discover -s tests -v
python3 -m http.server 4173 -d site
```

## Production configuration

Set these GitHub Secrets only:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_WIKI_PUBLIC_ROOT_TOKEN` — the `公开课程` Wiki node token

The Feishu self-built app needs published read permissions for the Wiki, document Blocks, and document media-download API, plus access to the selected Wiki space. The implementation deliberately does not require a Feishu public-share link, Bitable, a GitHub Actions variable, or a server.

## Public boundary

Everything placed directly under `公开课程` is copied into the public GitHub repository and GitHub Pages output, including document text and embedded files. Do not place confidential, copyrighted-for-internal-use, or credential-bearing material there. Keep drafts and internal files under `内部资料`.
