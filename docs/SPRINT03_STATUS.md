# Sprint 03 — VietBiz News editorial pipeline

Built on Sprint 02 source. Includes human/approved-model text draft submission, human publication, official-authority URL required for law category, basic public events endpoint and local CLI. **No live LLM translation service, Seznam API, legal fact checking, notifications or production authentication are connected.** A reviewed authority URL is a provenance control, not machine verification of the legal claim. Rights to reuse source content must be separately cleared before any feed is enabled.

Run from services/api: `python -m pytest -q`. Example CLI: `python news_pipeline.py draft ARTICLE_ID --title '...' --summary '...'`; then `python news_pipeline.py publish ARTICLE_ID --reviewer 'Editor' --authority-url https://eet.gov.cz/`.

Development-only X-User authentication still exists in original Sprint 01 API and makes this package unsafe to deploy publicly or to store real client financial records.
