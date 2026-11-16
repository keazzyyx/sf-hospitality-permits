.PHONY: dev dev-api dev-web install install-api install-web test test-api test-web test-precedent test-conditions lint lint-api lint-web catalog doctor build-api e2e ingest ingest-sf ingest-abc feedback-emails pg-test

API_DIR := apps/api
WEB_DIR := apps/web
VENV := $(API_DIR)/.venv
PY := $(VENV)/bin/python

install: install-api install-web

install-api:
	@test -d $(VENV) || uv venv -p 3.12 $(VENV)
	# requirements-lock.txt pins every Python dependency (uv pip compile --universal; see its header)
	cd $(API_DIR) && . .venv/bin/activate && uv pip install -r requirements-lock.txt -e "../../packages/precedent[dev]" -e ".[dev]"

install-web:
	pnpm install --frozen-lockfile

## make dev — runs the API (:8000) and the web app (:3000) together
dev:
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-api & \
	$(MAKE) dev-web & \
	wait

dev-api:
	cd $(API_DIR) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

dev-web:
	pnpm --filter web dev

test: catalog test-precedent test-api test-web test-conditions

test-precedent:
	cd packages/precedent && ../../$(VENV)/bin/pytest -q

test-api:
	cd $(API_DIR) && . .venv/bin/activate && pytest -q

test-conditions:   ## the local conditions search page: search rules and the built data (node --test)
	node --test tools/conditions-search/tests/*.test.mjs

test-web:
	pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web build

e2e:               ## Playwright smoke tests; installs the Chromium build Playwright needs on first run
	pnpm --filter web exec playwright install chromium
	pnpm --filter web test:e2e

lint: lint-api lint-web

lint-api:
	cd $(API_DIR) && . .venv/bin/activate && ruff check app tests && ruff format --check app tests && mypy app
	cd packages/precedent && ../../$(VENV)/bin/ruff check precedent tests && ../../$(VENV)/bin/mypy precedent

lint-web:
	pnpm --filter web lint && pnpm --filter web typecheck

catalog:
	python3 packages/catalog/scripts/validate.py

doctor:
	cd $(API_DIR) && . .venv/bin/activate && python -m neatlogs doctor --local --json

build-api:
	docker build -f $(API_DIR)/Dockerfile --build-arg GIT_SHA=$$(git rev-parse --short HEAD) -t permit-memo-api .

## Precedent data layer
# Ingest runs from the repo root, so its default store (data/) and raw folder (data/raw/) are <repo>/data: the folder
# the API's local store reads (apps/api/.env.example: PRECEDENT_DATA_DIR=../../data) and the nightly workflow uses.
# raw_ref stays a relative path (data/raw/...).
ingest:            ## full refresh of every source (PRECEDENT_DATABASE_URL → PostGIS, else local JSONL under ./data)
	$(PY) -m precedent.ingest --all

ingest-sf:         ## the SF sources one by one (first load); ABC for ZIP 94110 only unless ABC_ZIP_CODES is set
	export ABC_ZIP_CODES=$${ABC_ZIP_CODES:-94110} && for s in static datasf_zoning datasf_sud datasf_business datasf_planning datasf_entertainment abc sf_planning_hearings; do $(PY) -m precedent.ingest --source $$s || true; done

ingest-abc:        ## weekly, from a workstation: California ABC licenses (abc.ca.gov blocks GitHub runners); needs PRECEDENT_DATABASE_URL
	ABC_ZIP_CODES=$${ABC_ZIP_CODES:-94110} $(PY) -m precedent.ingest --source abc

feedback-emails:   ## send due 90-day outcome emails (dry run without RESEND_API_KEY)
	cd $(API_DIR) && . .venv/bin/activate && python -m app.jobs.feedback_emails

pg-test:           ## run the PostGIS store tests against PRECEDENT_TEST_DATABASE_URL
	cd packages/precedent && PRECEDENT_TEST_DATABASE_URL=$${PRECEDENT_TEST_DATABASE_URL:?set it to a PostGIS database} ../../$(VENV)/bin/pytest -q tests/test_store_postgres.py
