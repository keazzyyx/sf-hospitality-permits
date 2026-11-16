# apps/api — Permit Memo API

FastAPI + Anthropic SDK + Neatlogs. See the root README for architecture, env vars and deploy steps, and
`LOCAL_DEV.md` for the precedent ingestion / PostGIS setup behind the Location Risk Memo.

Layout: `app/agents` (checklist `AgentRunner`, memo `MemoRunner`), `app/tools` (catalog, timeline, fee, web_verify,
precedent tools), `app/memo` (deterministic analytics, store context), `app/routes` (plans, preview, memos, billing,
geocode/feedback/admin), `app/services` (plans, memos, billing, feedback, PDFs), `app/jobs` (feedback emails),
`app/scripts/memo_demo.py` (one real memo from the CLI).

```bash
cd apps/api
uv venv -p 3.12 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env            # fill ANTHROPIC_API_KEY at minimum
uvicorn app.main:app --reload   # http://localhost:8000/docs
pytest -q                       # 300+ tests, no network
ruff check app tests && mypy app
python -m neatlogs doctor --local --json
python -m app.scripts.memo_demo "995 Valencia St" "40-seat wine bar, small kitchen, until 1am, live music" --pdf /tmp/memo.pdf
```

Without Supabase configured the API falls back to an in-memory database (development only) and
auth still requires a valid Supabase JWT — generate one with your project's JWT secret, or run the
web app against a real Supabase project.
