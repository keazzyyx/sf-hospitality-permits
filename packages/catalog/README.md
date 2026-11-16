# @sfhp/catalog

The shared permit catalog: one JSON file per jurisdiction, validated against
`schema/permit.schema.json`. The API (`apps/api`) loads this directory at
startup; the web app imports the TypeScript types in `index.ts`.

## Layout

```
data/
  federal/us.json              # EIN, FDA/USDA items, music licensing (national orgs)
  states/<st>.json             # e.g. ca.json, ny.json, tx.json ... + _generic.json fallback
  cities/<city_slug>.json      # san_francisco.json, los_angeles.json, ...
  generic_city_checklist.json  # used when a city is unsupported
schema/permit.schema.json
scripts/validate.py            # python3 scripts/validate.py  (no deps)
```

## Permit entry

| field | meaning |
|---|---|
| `id` | `<prefix>.<slug>`; prefix is `us`, a state code (`ca`), or a city code (`sf`). Stable. Referenced by `prerequisites`. |
| `category` | one of the enum values in the schema (used for grouping + icons in the UI). |
| `jurisdiction_level` | `federal` / `state` / `county` / `city` (county items live in the city file). |
| `typical_timeline_days` | realistic calendar days from submitting a complete application to approval. |
| `fee_range_usd` | application + first-year fees. |
| `prerequisites` | permit ids that must be **approved** before this one can be **submitted**. Used for the dependency graph and critical path. |
| `applies_when` | rule over the `BusinessProfile` (see below). |
| `application_url` | real, direct URL. Checked by the `web_verify` tool at plan time. |
| `last_verified` | date the entry was last checked against the agency page. |
| `confidence` | `verified` = agency page confirmed fee/timeline/url. `estimated` = inferred from similar jurisdictions or unverified fee; the UI shows a badge. |
| `stall_risk` | optional; why this permit commonly delays openings and the mitigation. Feeds the blocker agent. |

## Rule DSL (`applies_when`)

```jsonc
{ "always": true }
{ "field": "serves_alcohol", "eq": true }
{ "field": "alcohol_type", "in": ["beer_wine", "full_liquor"] }
{ "field": "seats", "gte": 50 }
{ "all": [ ... ] }   { "any": [ ... ] }   { "not": { ... } }
```

Operators: `eq`, `neq`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`.
Comparisons against `null` fields evaluate to `false` (unknown ≠ true).

### BusinessProfile fields available to rules

| field | type | notes |
|---|---|---|
| `business_type` | `restaurant` \| `bar` \| `cafe` \| `food_truck` \| `hotel` \| `catering` \| `other` | wine bars / breweries → `bar`; bakeries / coffee → `cafe` |
| `city_slug`, `state` | string \| null | `san_francisco`, `CA` |
| `seats`, `square_feet`, `employees`, `hotel_rooms` | int \| null | |
| `serves_food` | bool | |
| `has_kitchen` | bool | any on-site food prep |
| `cooking_type` | `none` \| `limited` \| `full` | `full` = fryers / grills / hood → grease interceptor + hood suppression |
| `serves_alcohol` | bool | |
| `alcohol_type` | `none` \| `beer_wine` \| `full_liquor` \| `unknown` | `unknown`: serves alcohol, the description does not say what. A rule that turns on it is undetermined (never a match, never dropped): the checklist lists it with the condition under which it applies |
| `closes_after_midnight`, `closes_after_2am` | bool | |
| `live_entertainment`, `amplified_sound`, `dancing` | bool | |
| `outdoor_seating`, `sidewalk_or_parklet` | bool | `sidewalk_or_parklet` = public right-of-way |
| `change_of_use` | bool | previous occupant was not a restaurant/bar, or new build |
| `tenant_improvements` | bool | walls / plumbing / electrical / hood work |
| `new_construction` | bool | |
| `exterior_signage` | bool | |
| `plays_recorded_music` | bool | background music counts |
| `mobile_vending`, `uses_commissary` | bool | food trucks / carts |
| `sells_packaged_goods` | bool | retail of taxable goods |
