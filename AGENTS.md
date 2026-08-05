# Repository Guidelines

## Project Structure

This repository publishes complete COOC courses as a static site. `site/` is the GitHub Pages artifact: the catalogue lives in `site/data/courses.json`; generated courses, images, and downloadable files live under `site/courses/`. `scripts/sync_feishu_wiki.py` is the ongoing content synchronizer. `scripts/import_cooc_china.py` initializes the official course catalogue, and `scripts/import_embedded_system_book.py` is a guarded, idempotent full-text initializer for the authorized `Embedded-System-Development-Book`; neither is part of the recurring publish path. `samples/` contains non-sensitive Feishu API fixtures, and `tests/` verifies filtering, block rendering, media export, and withdrawal cleanup.

## Development Commands

```sh
# Generate a complete offline course site from the fixture
python3 scripts/sync_feishu_wiki.py --input samples/feishu-wiki-nodes.json

# Rehearse the one-time 20-course import without writing Feishu
python3 scripts/import_cooc_china.py --source-directory /path/to/posts --dry-run

# Run all publication tests
python3 -m unittest discover -s tests -v

# Preview the generated static site
python3 -m http.server 4173 -d site
```

## Style and Publication Rules

Use four-space Python and two-space HTML/CSS/JavaScript indentation. Keep the synchronizer standard-library only. A course is public only when it is a direct `docx` child of the configured `公开课程` Wiki node. Numeric prefixes such as `001-课程名称` control ordering but are omitted from visible titles.

飞书（Feishu） is an editing source only: generated public pages must never link back to `*.feishu.cn`, expose document or node tokens, or depend on visitor sign-in. Downloaded images and attachments must be stored within the matching `site/courses/<course>/assets/` directory. Unsupported leaf Block types must fail the sync rather than silently omit content.

## Testing and Review

Run the fixture sync and all tests before review. Verify a generated course page contains its body, local images, and local download links; verify removing a course removes its static directory. Add a fixture and test for every newly supported Feishu Block shape.

## Automation and Deployment

`.github/workflows/sync-feishu.yml` runs on schedule or manually, commits only generated `site/` changes, then deploys GitHub Pages. `.github/workflows/import-cooc-china.yml` is manual-only and requires an exact confirmation value before creating missing initial course documents; it never commits site content. Credentials belong only in GitHub Secrets: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and `FEISHU_WIKI_PUBLIC_ROOT_TOKEN`. The Feishu app needs published read access to the Wiki, document Blocks, and document media download APIs. Never log tokens, private URLs, or source content outside the intended public output.
