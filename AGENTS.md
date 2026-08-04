# Repository Guidelines

## Project Structure

This repository publishes a COOC course catalogue as a static site. `site/` is the deployable artifact: `index.html`, `styles.css`, `app.js`, and generated `site/data/courses.json`. `scripts/` contains the Feishu Bitable synchronizer; `samples/` holds non-sensitive API-shaped fixtures; `tests/` verifies data normalization and publication filtering. `docs/` records the Bitable schema and platform-specific deployment decisions.

## Development Commands

```sh
# Generate public data from the fixture
python3 scripts/sync_feishu_bitable.py --input samples/feishu-records.json

# Run unit tests
python3 -m unittest discover -s tests -v

# Preview the static site
python3 -m http.server 4173 -d site
```

The production sync reads `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_BITABLE_APP_TOKEN`, and `FEISHU_BITABLE_TABLE_ID` from the environment. Never write those values, private Feishu URLs, or attachment tokens to files or logs.

## Style and Data Rules

Use four spaces in Python and two spaces in HTML/CSS/JavaScript. Keep Python standard-library only unless a dependency is justified. Field names follow the schema in `docs/field-schema.md`; generated records use `snake_case`. A record is publishable only when `公开发布` is true and its `飞书公开文档链接` is an HTTPS `*.feishu.cn` URL. Unpublished or malformed records must not reach `site/data/courses.json`.

## Testing and Review

Run the generator and unit tests before review, then open the local site and verify that only published cards render. When changing the Bitable mapping, add a fixture and test for the new field shape. Pull requests should state the affected schema, whether public data changed, and screenshots for visible layout changes.

## Automation and Deployment

`.github/workflows/sync-feishu.yml` performs scheduled or manual synchronization; GitHub Secrets hold all credentials. Do not enable a public deployment, create a remote repository, or expose a Feishu document until the target owner, visibility, and rollback path are confirmed.
