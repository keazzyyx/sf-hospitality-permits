# Permit Memo web (`apps/web`)

Next.js 15 (App Router, `src/`), TypeScript strict, Tailwind CSS v4, shadcn/ui, Supabase auth, PostHog, Leaflet, Playwright.
The app is a thin, typed client over the FastAPI backend described in [`docs/api-contract.md`](../../docs/api-contract.md)
(permit checklists, the free tier) and [`docs/api-contract-memo.md`](../../docs/api-contract-memo.md) (the paid
**Location Risk Memo**: every approval your concept needs at an address, with the rules and records behind each,
and what's still unknown).

## Run it

```bash
# from the repo root
pnpm install
cp apps/web/.env.example apps/web/.env.local   # fill in Supabase keys (optional for the public pages)
pnpm dev:web                                   # http://localhost:3000, expects the API on :8000
```

Quality gates (all must be green):

```bash
pnpm --filter web lint        # eslint --max-warnings=0 (next/core-web-vitals + typescript)
pnpm --filter web typecheck   # tsc --noEmit
pnpm --filter web build
pnpm --filter web exec playwright install chromium   # once
pnpm --filter web test:e2e    # starts `next dev` on :3100 (or reuses it), chromium only
```

The smoke suite (`e2e/smoke.spec.ts`) runs with Supabase variables unset and needs no backend: it route-mocks
`POST /v1/preview` (hand-written `text/event-stream`), `GET /v1/geocode` and `GET|POST /v1/feedback/{token}`, and
renders the memo page through the development-only fixture route described below.

## Environment variables

| name | required | default | purpose |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | for auth | – | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | for auth | – | Supabase anon key |
| `NEXT_PUBLIC_API_URL` | no | `http://localhost:8000` | FastAPI base URL |
| `NEXT_PUBLIC_SITE_URL` | no | `http://localhost:3000` | canonical origin for metadata |
| `NEXT_PUBLIC_POSTHOG_KEY` | no | – | PostHog project key; analytics are a no-op when empty |
| `NEXT_PUBLIC_POSTHOG_HOST` | no | `https://us.i.posthog.com` | PostHog host |

No key is needed for the map: comparable cases render on OpenStreetMap tiles through Leaflet.

Without the two Supabase variables the app still builds and serves: `/`, `/checklist` (including the anonymous
preview), `/feedback/[token]`, `/privacy`, `/terms` work; `/login` shows a "sign-in is not configured" notice;
`/app/*` redirects to `/login`.

## How it fits together

### Routes

| route | what |
|---|---|
| `/` | Landing for the memo: hero with an address field (autocomplete from `GET /v1/geocode?q=`, keyboard navigable, shows parcel/zip) and a concept textarea → `/memo?address=…&lat=…&lng=…&description=…`. Sections: how it works (records → precedent → memo), what's in a memo (sample card with blurred comparables), pricing (Free / Operator $499 per memo / Pro $299 per month), coverage (SF now, LA & NYC next; lead capture via `POST /v1/leads`), trust notes. Secondary CTA and nav item "Free permit checklist" → `/checklist`. |
| `/checklist` | The free tier: the former landing, unchanged in behaviour. "Describe your business" textarea, sample prompts, target date; streams `POST /v1/preview` in place, clarifying questions, permit preview + auth-gate card, lead capture for unsupported cities. |
| `/memo` | Public entry point. Server redirect to `/app/memo` with the same query; the middleware sends signed-out visitors to `/login?next=…`. |
| `/login` | Magic link (`signInWithOtp`) and Google (`signInWithOAuth`). No passwords. |
| `/auth/callback` | Route handler: exchanges `?code=` (PKCE) or `?token_hash=&type=` for a session, then redirects to `?next=`. |
| `/app` | Authenticated shell (sidebar: Memos / New memo / Bulk upload (Pro) · Permit checklists / New checklist · Billing · Admin when `me.is_admin`). Redirects to `/app/memos`. |
| `/app/memos` | Memo list: cards with address, concept, overall status pill (or an "Earlier format" tag), teaser/full badge, date, batch tag. Also resumes a pending memo (`pp_pending_memo`) or pending preview (`pp_pending_preview`) saved before sign-in. |
| `/app/memo` | New memo. Step 1 address (autocomplete) + concept; step 2 streams `POST /v1/memos` with stage/tool progress (stages `intake, records, precedent, risk, finalize`; tool lines show `rows`), clarification form → `POST /v1/memos/{id}/clarify`, `narrative` streams into the memo box; on `memo` → `/app/memos/[id]`. `402 paywall_memo` → paywall screen with the two offers; `422 outside_coverage` / `address_not_found` inline. Prefills from the query or `pp_pending_memo` and auto-starts. |
| `/app/memos/[id]` | Memo page. Header: address, concept, overall status pill with the overall line, generated date, Export PDF (full only), Re-run (prefilled `/app/memo`; on an earlier-format memo it carries `rerun_of`), delete. Teaser: overall status + counts, unlock card (instant `POST /v1/memos/{id}/unlock` when `memo_credits > 0` or Pro, otherwise Stripe Checkout `mode: memo | pro` returning to `?checkout=success`, which auto-unlocks), blurred skeleton preview. Full (report format 3): one row per approval with its status, rule lines and facts, what the rules could not settle, site history, comparable cases (Leaflet map + table), zoning & overlays, outcome counts, status definitions, citations. Earlier format: the re-run card (the first re-run of a memo the user unlocked is free, `rerun_free`). Every `citations: string[]` renders as `[n]` superscripts that scroll to the footnote. |
| `/app/memos/bulk` | Pro only (otherwise an upsell card). CSV upload (`address,description`, max 25 rows, client-side template download) → `POST /v1/memos/bulk` → batch page. |
| `/app/memos/bulk/[batchId]` | Polls `GET /v1/memos/bulk/{batch_id}` every 5 s; status and overall status per memo with links; CSV export of the batch. |
| `/app/plans`, `/app/new`, `/app/plans/[id]` | Permit checklists (free tier): list, new checklist (streams `POST /v1/plans`), detail with Checklist / Timeline / Dependencies / Fees / Blockers tabs. |
| `/app/billing` | Memo entitlement (`pro_status`, `memo_credits`, `free_teasers_remaining`) with the Operator ($499 memo credit) and Pro ($299/mo) offers, plus the checklist entitlement and the $29 / $49 checklist offers; Stripe portal. `?checkout=success` fires `upgrade` and refreshes `GET /v1/me`. |
| `/app/admin` | Visible in the nav only when `me.is_admin` (missing = false). `GET /v1/admin/overview`: ingestion runs table, row counts by table/source, feedback stats, memo stats, users. A `403` renders "Admins only". |
| `/feedback/[token]` | Public, no auth. `GET /v1/feedback/{token}` → address + concept, five outcome buttons + notes → `POST`; thank-you and already-answered states. |
| `/privacy`, `/terms` | Static. |
| `/dev/memo-preview` | **Development only.** Renders `MemoView` against `src/lib/fixtures/memo-fixture.ts` (`?access=teaser|full&me=free|credit|pro`; the `variant=` values, among them a report stored before rule table v2 and one generated after its rules date, are listed at the top of the file). The file is `page.dev.tsx`; `next.config.ts` registers the `dev.tsx` page extension only when `NODE_ENV !== "production"`, so the route is absent from production builds (check the route table printed by `next build`). |

### Auth

`@supabase/ssr` cookie sessions.

- `src/lib/supabase/client.ts` browser singleton + `getAccessToken()`.
- `src/lib/supabase/server.ts` server-component/route-handler client + `getServerUser()`.
- `src/lib/supabase/middleware.ts` + `src/middleware.ts` refresh the session on every request and redirect
  unauthenticated `/app/*` traffic to `/login?next=…` (also when Supabase is unconfigured).
- `src/components/app/app-shell.tsx` waits for the browser session and provides `{ user, accessToken, me }`
  to every `/app` page via `useApp()`; tokens refresh through `onAuthStateChange`.
- After the first sign-in on a browser the `signup` event fires once (localStorage flag) and the user is
  identified in PostHog by their Supabase id.

**Supabase dashboard setup**: Authentication → URL configuration → add
`https://<your-domain>/auth/callback` (and `http://localhost:3000/auth/callback`) to *Redirect URLs*, set
*Site URL* to your domain, enable the Email provider (magic link) and the Google provider (OAuth client
from Google Cloud with `https://<project-ref>.supabase.co/auth/v1/callback` as the authorised redirect).

### Streaming

`src/lib/api.ts` exports `streamSSE(path, body, { token, onEvent, signal })`: a `fetch` POST with the
bearer token that reads the body with a `ReadableStream` reader, buffers partial chunks, normalises CRLF,
splits frames on blank lines, joins multi-line `data:` fields, JSON-parses and calls `onEvent(name, data)`.
Pre-stream rejections (`401`, `402 paywall` / `paywall_memo`, `429 rate_limited`, `422 not_hospitality` /
`outside_coverage` / `address_not_found`) surface as a typed `ApiError { status, code, message, extra }`.

`src/hooks/use-generation-stream.ts` reduces the events into `{ stages, narrative, clarification, preview,
plan, memo, error }` (plus `planId` / `memoId`); the same hook drives the checklist preview, `/app/new`,
`/app/memo`, clarifications and reruns. `STAGE_LABELS` covers the checklist stages; `MEMO_STAGE_LABELS`
("Reading your concept", "Pulling records within 500 ft and 1,000 ft", "Ranking comparable cases", "Writing the
memo") is passed to `StageProgressList` via its `labels` prop. Tool events with `rows` show a row-count chip.

### Memo page components

`src/components/memo/memo-view.tsx` is pure: it takes `MemoRecord` + `Me` (+ optional GeoJSON and action
callbacks) and renders the teaser or the full memo. `memo-detail.tsx` is the data layer for `/app/memos/[id]`
(fetch, poll while generating, `map.geojson`, unlock, checkout return, PDF export, delete). Citations use a
context (`CitationProvider` / `Cite` / `CitationList`) that numbers `memo.citations` in order and resolves
every `citations: string[]` to `[n]` links.

**Leaflet**: `comparables-map.tsx` imports `leaflet` and `react-leaflet` (which touch `window`), so it is
loaded through `comparables-map-lazy.tsx` with `next/dynamic` and `ssr: false`. Tiles come from
`tile.openstreetmap.org` (no API key; keep the attribution). Markers are `divIcon` / `CircleMarker`, so no
image assets are needed. The subject marker, 500 ft / 1,000 ft rings and comparable cases come from the
memo; overlay polygons come from `GET /v1/memos/{id}/map.geojson` and are styled by `properties.kind`.

### Anonymous input → first result

- Checklist: when the `/checklist` preview completes, `{ preview_id, description, target_open_date }` is stored
  under `pp_pending_preview`. After sign-in, `/app/memos` redirects to `/app/new`, which streams
  `POST /v1/plans { …, preview_id }`. The key is cleared once `plan_created` arrives.
- Memo: the landing hero stores `{ address, description, lat, lng }` under `pp_pending_memo` and sends
  signed-out visitors to `/login?next=/memo`. After sign-in, `/app/memo` reads the query or the pending memo
  and starts `POST /v1/memos` immediately. The key is cleared once `memo_created` arrives; a `402` keeps it so
  the memo resumes after checkout (`/app/memo?checkout=success`).

### Paywalls

- Checklists: `POST /v1/plans` returns `402 { code: "paywall" }` after 3 free plans → `PaywallCard`
  (`mode: "plan"` $29, `mode: "subscription"` $49/month).
- Memos: `POST /v1/memos` returns `402 { code: "paywall_memo" }` once the free teasers are used →
  `memo_paywall_hit` and the two offers (`mode: "memo"` $499 one-time credit, `mode: "pro"` $299/month).
  Unlocking a teaser calls `POST /v1/memos/{id}/unlock` when `memo_credits > 0` or `pro_status ∈ {active,
  trialing}`; otherwise Checkout returns to the memo with `?checkout=success` and the page unlocks it.

### Analytics

`src/lib/analytics.ts` wraps `posthog-js`. Events: `plan_started`, `plan_completed`, `signup`, `paywall_hit`,
`upgrade`, `preview_started`, `preview_completed`, `clarification_shown`, `step_toggled`, `pdf_exported`,
`lead_captured`, `memo_started`, `memo_completed`, `memo_teaser_viewed`, `memo_unlocked`, `memo_paywall_hit`,
`memo_pdf_exported`, `bulk_uploaded`, `feedback_submitted`.

## Deploy to Vercel

- Import the repo, set **Root Directory** to `apps/web`, and enable **Include source files outside of the
  Root Directory** (needed for the pnpm workspace and `packages/catalog`).
- `apps/web/vercel.json` already sets `installCommand: cd ../.. && pnpm install --frozen-lockfile` and
  `buildCommand: cd ../.. && pnpm --filter web build`; the framework preset is Next.js.
- Add the environment variables above (Production + Preview). `NEXT_PUBLIC_SITE_URL` should be the
  production origin; auth and Stripe redirects use `window.location.origin`, so preview deployments work
  as long as their origins are in Supabase's redirect allow-list (a wildcard like
  `https://*-yourteam.vercel.app/auth/callback` is accepted there).
- Node 20+ runtime (the repo is developed on Node 26); pnpm is read from the root `packageManager` field.
