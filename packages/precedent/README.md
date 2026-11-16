# packages/precedent — the precedent data layer

Ingests San Francisco permit, license, zoning and hearing records into PostGIS (Supabase) and
answers the spatial questions the Location Risk Memo needs: what was applied for near this address,
what got approved / denied / conditioned, what overlays and zoning rules apply, how dense the
alcohol / food scene already is.

```
precedent/
  models.py          Application · Location · Overlay · Business · OutcomeFeedback · IngestionRun
  sources/           one module per source: fetch(raw) + parse(raw → SourceBatch), rate-limited
  store/             Store protocol; LocalStore (JSONL + shapely) and PostgresStore (PostGIS, psycopg3)
  store/schema.sql   PostGIS tables (also applied by supabase/migrations/20261022000000_precedent.sql)
  textparse.py       use types, closing hours, conditions, opposition heuristics (unit-tested)
  geocode.py         Geocoder contract; geocode_sf.py = DataSF EAS + Nominatim fallback
  ingest.py          `python -m precedent.ingest --all` (nightly job) — idempotent upserts
  static/            Planning Code rule rows with citations
tests/fixtures/<source>/   real sample responses the parsers are tested against
```

Run: `python -m precedent.ingest --list`, `--source datasf_planning`, `--all`, `--parse-only <raw file>`.
Env: `PRECEDENT_DATABASE_URL` (PostGIS; omitted → local store in `PRECEDENT_DATA_DIR`), `PRECEDENT_RAW_DIR`,
`SOCRATA_APP_TOKEN` (optional, raises DataSF rate limits), `NEATLOGS_API_KEY` (ingestion spans).

Adding a city: new `sources/<city>_*.py` modules producing the same models, a rules file under `static/`,
and a geocoder for that city's address dataset. Nothing in the store or the memo chain is SF-specific.
