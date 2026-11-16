# 995 Valencia on rule table v2: five runs side by side

Run 2026-11-11 on the final code (commit 8e4847e), five reports at once, against the local copy of the records,
with the production models. Nothing was written to production. Files: [`final5/`](final5/) (each run's report as
JSON and PDF, the intake profile the rules read, token usage by stage, and every citation-check call).

Address and concept: 995 Valencia St, "40-seat wine bar, small kitchen, open until 1am, occasional live music".
No intake questions answered.

## Statuses

| | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
|---|---|---|---|---|---|
| Zoning and use | Further review | Further review | Further review | Further review | Further review |
| Alcohol licence | Insufficient information | Insufficient information | Insufficient information | Insufficient information | Insufficient information |
| Entertainment permit | Further review | Further review | Further review | Further review | Further review |
| Health permit | Allowed | Allowed | Allowed | Allowed | Allowed |
| Building permit and change of use | Further review | Further review | Further review | Further review | Further review |

**Five identical sets.** Compared by program, the five also match on every approval name and agency, every rule
line word for word, every trigger with its control and missing inputs, the three change-of-use answers, the
overall line, the list of approvals to file, and the intake profile on every field the rules read.

## What each row says and why

- **Zoning and use: Further review** (Conditional Use Authorization, Planning Code § 303). A Bar is a conditional
  use in NCT-VALENCIA (§ 762), and a new Bar in the Mission Alcoholic Beverage Special Use District is always a
  conditional use (§ 249.60). Three questions the description does not answer are named but do not change the
  status, because a hearing is needed either way: whether the business is part of a chain (formula retail),
  whether there is entertainment and what kind, and the floor area (use size).
- **Alcohol licence: Insufficient information.** Not given: "how the liquor licence will be obtained (new, or a
  transfer from another owner or another location)". Still printed on the row: the licence type the description
  points to (Type 42, on-sale beer and wine; "wine bar" says what is served), the Mission rule that a new Bar
  must use a licence transferred from another Bar inside the district, and the census tract figures (tract
  208.01: 28 active on-sale licences against 12 authorised), with the line that state law tests concentration
  only for a new licence or a transfer from another location, which the description does not say.
- **Entertainment permit: Further review.** "Occasional live music" does not say which permit; the row names the
  three that could apply and lists the review steps inside them on today's rules, including those Ordinance 118-25
  removed (shown as ended, not as approvals that ended).
- **Health permit: Allowed.** Plan check, inspection and a permit to operate.
- **Building permit and change of use: Further review.** The three answers, each on its own line:
  - Planning Code change of use: **yes**. The active Type 41 licence on file at 995 Valencia St reads the space as a
    Restaurant; Restaurant to Bar is a change of use.
  - Building Code change of occupancy: **not established**. 40 seats is not an occupant load, and the existing
    occupancy group is not in public records.
  - Neighbourhood notification: **not required** under the rule in force.

## What changed to get identical sets

The first five runs, an hour earlier ([`final5-first/`](final5-first/)), already had identical statuses, but not
identical rule lines. The intake model, which reads the description into the facts the rules use, guessed two
facts the description does not state: in one run of five it read the wine bar as "not part of a chain", and in
three it read "40 seats" as "fewer than 50 occupants". Those facts now come only from the applicant's answers to
the intake questions; the model is not shown them and anything it puts there is dropped. A test pins this.

## Sentences the citation check changed

Of 180 cited sentences across the five runs:

| Outcome | Share |
|---|---|
| Kept as written | 15% |
| Cut down to the supported part | 31% |
| Lost its citation and its label | 29% |
| Removed (an expected condition or filing step) | 26% |

The statuses, rule lines and missing inputs are set by rules and are not touched by the check. The writer's
explanations still overreach their records about half the time; the check removes what it cannot support.

## Cost

| | |
|---|---|
| Per report | $1.94 on average ($1.87 to $2.01) |
| By stage | citation check 45%, writer 23%, comparables 18%, records 11%, intake 3% |
| Time | 8 to 10 minutes per report, all five at once |
| These five runs | $9.69 (the first five: $10.15) |
