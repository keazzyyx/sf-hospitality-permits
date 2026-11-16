# Local development

## Prerequisites
- Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 20+ + pnpm, `make`.
- Optional: PostgreSQL 16/17 with PostGIS for the precedent store (`brew install postgresql@17 postgis`); without it the
  API uses a file-backed store under `./data` (same semantics, slower, fine for development).
- Keys: `ANTHROPIC_API_KEY` (required to generate anything), Supabase project (auth + plans tables), Stripe test keys,
  `NEATLOGS_API_KEY` (optional locally), `RESEND_API_KEY` (optional; feedback emails dry-run without it).

## First run
```bash
make install                                  # api venv (+ packages/precedent editable), pnpm install
cp apps/api/.env.example apps/api/.env        # fill in keys; leave PRECEDENT_DATABASE_URL empty for the local store
cp apps/web/.env.example apps/web/.env.local
make ingest-sf                                # ~40 min: zoning/SUD polygons, rules, businesses, Planning + Entertainment permits, ABC (ZIP 94110), hearings
make dev                                      # API :8000, web :3000
```
`make ingest-sf` writes raw responses to `./data/raw/<source>/` and snapshots to `./data/snapshots/*.jsonl`.
Re-running is idempotent (upsert by id). `python -m precedent.ingest --list` shows sources and rate limits;
`--source <name>` runs one; `--parse-only data/raw/<source>/<file>` prints what a raw file parses to.

Knobs for a first load (all optional): `DATASF_MAX_PAGES=2` caps Socrata paging per dataset, `DATASF_MAX_CODES=10`
caps zoning codes, `PLANNING_HEARINGS_MAX_DOCS=20` / `PLANNING_HEARINGS_MAX_REQUESTS=100` cap the hearing-PDF source
(default 150 docs / 450 requests ≈ 15 min per nightly run, newest first; about a week of nightly runs covers five years),
`PLANNING_HEARINGS_REEMIT=1` re-emits every cached hearing sidecar (rebuilding a fresh store), `ABC_ZIP_CODES=94110,94103`
limits the ABC pull to a few ZIP codes, `SOCRATA_APP_TOKEN` raises DataSF rate limits.

Sources and datasets: Planning records `y673-d69b` (+ parcels `acdm-wktn` for points/zoning), Active Entertainment
Permits `86e8-rfem`, Registered Business Locations `g8m3-pdis`, Zoning Districts `3i4a-hu95`, Special Use Districts
`5yf5-ms5f`, California ABC license lookup (see `precedent/sources/abc.py` header for the access path and rate limit),
Planning Commission adopted motions via the PIM document service + adopted minutes PDFs (`sf_planning_hearings.py` header).

## Using PostGIS locally
```bash
brew services start postgresql@17            # or pg_ctl
createdb sfhp_local && psql sfhp_local -c "create extension postgis"
export PRECEDENT_DATABASE_URL=postgresql://localhost/sfhp_local
make ingest-sf                                # schema is created automatically (packages/precedent/precedent/store/schema.sql)
```
The API picks the same URL up from `apps/api/.env`. For Supabase, use the **session pooler** connection string from
Project Settings → Database and enable PostGIS once (`create extension postgis;` in the SQL editor), or just run
`supabase db push` which applies `supabase/migrations/20261022000000_precedent.sql`.

## Tests
```bash
make test                   # catalog validator, precedent parsers/local store, API suite, web lint/typecheck/build
make e2e                    # Playwright smoke (web)
PRECEDENT_TEST_DATABASE_URL=postgresql://localhost/sfhp_test make pg-test   # PostGIS store tests (CI runs them in a postgis container)
make doctor                 # python -m neatlogs doctor --local --json
```
The API suite never touches the network: the Anthropic client is scripted (`apps/api/tests/fakes.py`,
`tests/memo_fakes.py`), the store is a seeded `LocalStore` around 995 Valencia St, and the geocoder is faked.

## Generating a real memo from the command line
```bash
cd apps/api && source .venv/bin/activate
python -m app.scripts.memo_demo "995 Valencia St" "40-seat wine bar, small kitchen, open until 1am, occasional live music" --pdf /tmp/memo.pdf
```
This runs the full chain against the local store and the real model, prints the memo JSON, and writes the PDF.

## Jobs
- `make ingest` — full refresh. The GitHub Action `.github/workflows/ingest.yml` runs it with `--skip abc` when started
  by hand (add a schedule to run it nightly).
- `make ingest-abc` — **run weekly from a workstation** with `PRECEDENT_DATABASE_URL` set to the Supabase pooler URL: abc.ca.gov
  returns 403 to GitHub's hosted runners, so the nightly job skips California ABC and prints a warning with the date
  the ABC rows were last refreshed. `ABC_ZIP_CODES` defaults to 94110.
- `make feedback-emails` — 90-day outcome emails (same cron service runs it after ingestion).

## Troubleshooting
- `postmaster became multithreaded during startup` on macOS → `export LC_ALL=C` before starting Postgres.
- `address_not_found` for an SF address → check the EAS geocoder: `python -c "import asyncio; from precedent.geocode_sf import SFGeocoder; print(asyncio.run(SFGeocoder().geocode('995 Valencia St')))"`.
- Memo fails with "structured output failed validation 3 times" → the intake model kept submitting a profile or quotes
  that do not validate; the Neatlogs trace for `agent.intake` shows the rejected inputs.

## Auth emails

Sign-in links are verified server-side (`/auth/callback`, token hash or implicit fragment via
`/auth/complete`), so a link requested in one browser can be opened in another. The hosted project's
email templates live in `supabase/templates/`; push them with `supabase/push-auth-templates.sh` (needs
a custom SMTP sender on the free tier, see `supabase/README.md`). Against the hosted project, Site URL is
production, so a link requested from localhost lands on the production callback: use the 6-digit code
from the email on the local login page instead.
