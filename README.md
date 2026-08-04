# COOC Feishu Publisher

A static COOC catalogue whose public entry point is a code-hosted site while course metadata and long-form material are managed in Feishu.

## Content flow

```text
Feishu Bitable (published course metadata)
  -> sync_feishu_bitable.py
  -> site/data/courses.json
  -> static site / GitHub Pages
  -> public visitor
```

Each published card may link to a separately published Feishu document for full collaborative material. The site never exposes unpublished rows, secrets, or private Feishu links.

## Local verification

```sh
python3 scripts/sync_feishu_bitable.py --input samples/feishu-records.json
python3 -m unittest discover -s tests -v
python3 -m http.server 4173 -d site
```

Open `http://127.0.0.1:4173/`. The fixture intentionally includes one unpublished row; it must not appear.

## Production credentials

Set the following only in the shell or GitHub Secrets:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_BITABLE_APP_TOKEN`
- `FEISHU_BITABLE_TABLE_ID`

Run `python3 scripts/sync_feishu_bitable.py` without `--input` to fetch Feishu Bitable records. See `docs/field-schema.md` before configuring the table.
