# VietBiz Sprint 02 — News foundation

Completed: SQLite migration-on-startup, RSS/Atom metadata parser, source-domain allowlist, deduplication, categorization, Vietnamese editorial publication via local CLI, read-only public API, simple News Feed frontend, automated tests.

Unimplemented / not verified: a licensed Seznam API, live feed sync, automatic AI translation, automated legal fact-checking, push notifications, image licenses, production authentication or deployment.

**Source control:** Newsfeed documentation at https://vyvojari.seznam.cz/newsfeed/dokumentace explains a publisher-to-Seznam feed, not unrestricted extraction from Seznam. Example Novinky source is disabled until terms and permissions are approved.

Use `python -m pytest -q` from `services/api` to verify. Run `uvicorn app.main:app --reload` and `python -m http.server 3000 --directory apps/news-web` from project root in separate terminals. To see items: `cd services/api`, import `python news_editor.py sample --file tests/fixtures/sample.xml`, run `python news_editor.py pending`, and then publish an original Vietnamese description reviewed by editor.
