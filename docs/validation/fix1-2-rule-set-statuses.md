# Fixes 1 and 2: the pathway and every status set by rules

Built and run 2026-11-10. Everything is local: nothing on `main`, nothing written to production.

Runs: [`fix12/`](fix12/) holds the five reports (JSON and PDF), the intake profile each run used, token usage,
and every citation-check call with its verdict and what the report finally shows.

## 1. What changed

- **The pathway comes from a rule lookup in code** (`apps/api/app/memo/pathway.py`): zoning district, special
  use districts, the use, the hours, and the licences on file at the address. It decides whether the concept is
  permitted, a conditional use or not permitted, and whether it is a change of use.
- **Every row's status is set by rule** from those facts. So are the name of each approval, the agency, the
  overall line and the list of approvals to file.
- **The writer model only explains.** Its tool no longer has a status, an approval name, an agency, an overall
  line or a path to fill in. Every row explanation is checked against that row's rule lines; one that states a
  different status, pathway or change-of-use answer is replaced.
- **The building row takes its change-of-use answer from the zoning row.** They read the same value, so they
  cannot disagree.
- **The citation check can no longer change a status.**
- **A partly supported sentence is cut down to the supported part**, then checked again. If the cut text is
  still not fully supported, the sentence loses its citation (a finding) or is removed (a condition or filing
  step). No sentence is kept whole with a "partly supported" note.
- **The intake step runs at temperature 0**, because the profile it produces feeds the rules.

## 2. Five runs of 995 Valencia, side by side

Same address, same concept ("40-seat wine bar, small kitchen, open until 1am, occasional live music"), intake
re-run each time.

| | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
|---|---|---|---|---|---|
| Zoning and use | Further review | Further review | Further review | Further review | Further review |
| Alcohol licence | Potential blocker | Potential blocker | Potential blocker | Potential blocker | Potential blocker |
| Entertainment permit | Further review | Further review | Further review | Further review | Further review |
| Health permit | Allowed | Allowed | Allowed | Allowed | Allowed |
| Building permit and change of use | Further review | Further review | Further review | Further review | Further review |
| Overall | Potential blocker | Potential blocker | Potential blocker | Potential blocker | Potential blocker |

**Five identical sets. No row varies.** Also identical across the five, compared by program:

- the pathway: Bar, conditional use, existing use Restaurant, change of use yes;
- every approval name and agency;
- every rule line under every row, word for word;
- the overall line and the list of approvals to file;
- the intake profile, on all sixteen fields the rules read.

The rule lines for this address:

- The concept is looked up as a Bar (Planning Code § 102).
- Zoning district NCT-VALENCIA: a Bar is a conditional use (§ 762).
- An active ABC Type 41 licence is on file at 995 Valencia St, so the rules read the space as a Restaurant.
  Restaurant to Bar is a change of use.
- Mission Alcoholic Beverage Special Use District: a new Bar must use a licence transferred from another Bar
  inside the district (§ 249.60). That is the potential blocker.

The building row now reads Further review, where the Part 3 report said Allowed with "no change of use is
assumed". That was the inconsistency a review flagged.

What can still vary: the writer's explanations, findings, conditions and filing steps, and the timeline and
cost figures. Those are model text, checked sentence by sentence.

## 3. Share of sentences downgraded

Across the five runs, 200 cited sentences were checked.

| Outcome | Sentences | Share |
|---|---|---|
| Kept as written | 37 | 18% |
| Cut down to the supported part, label and citation kept | 72 | 36% |
| Lost its citation and its label (a finding) | 45 | 22% |
| Removed (an expected condition or filing step) | 46 | 23% |

So **45% of cited sentences are downgraded or removed**, 36% survive in a shorter form, and 18% stand as
written. In Part 3 the comparable figure was a third to a half downgraded, but those sentences were kept whole
with a note; now nothing partly supported is shown whole.

Why the rate is this high, from the three runs I broke down (115 sentences):

- 13 were unsupported outright.
- 84 were partly supported. 41 were cut down successfully.
- Of the 43 that could not be cut: in 24 the second check found the shortened sentence still went beyond its
  record; in 19 the guard rejected the cut (the checker reworded it, kept a part it had itself flagged, broke
  the "condition / basis" layout, or returned nothing).

The writer is still the weak point: it joins a real record to a conclusion the record does not state. The check
now removes those, at the cost of a thinner report. Two things would recover content without loosening the
standard, neither done yet: a second cut round where the first cut still overreaches, and a tighter writer
prompt for filing steps, which fail most often.

Run-to-run spread: kept as written 5 to 12; cut 12 to 18; lost citation 4 to 13; removed 7 to 11.

## 4. Pathway tests from the Planning Code

22 address and concept pairs across 16 zoning districts are in
`apps/api/tests/fixtures/pathway_cases.json`. For each, one reader wrote down the expected pathway from the
Planning Code text with quotes, and a second reader re-derived it without seeing the first.

| Result | Cases |
|---|---|
| The rules give the Code's answer | 14 |
| Right on the best case; the Code's answer turns on a fact not on file | 3 |
| Known gap, kept as a failing test so it stays visible | 4 |
| Disputed: Code text and Planning practice differ | 1 |

- **Best case only (3):** restaurants in the Mission Street and 24th Street districts and in North Beach, where
  a cap or a prior-use rule can turn "conditional" into "not permitted".
- **Known gaps (4):** a beer-and-wine bar in the Bayview district (the rules say not permitted, the Code says
  conditional for that licence type); a restaurant closing between 10 p.m. and midnight where permitted hours
  end at 10 p.m.; a café with no alcohol (Limited Restaurant, not in the table); a bar whose late hours are
  already lawful. All four are in the rule-table extension.
- **Disputed (1):** a restaurant east of Mission Street inside the Mission alcohol district. It is out of the
  pass/fail count until Planning answers in writing, and will read "Further review: Code and Planning practice
  differ".

The readings also produced 25 corrections to our zoning rule table, each with a Code quote. They are applied to
the rules file and to the local database only.

## 5. Review

Six reviewers went through the work by dimension and every finding was checked by a second agent: 37 findings,
all confirmed, 36 fixed. The ones that mattered most:

- A row explanation that cited no record was never checked, so it could contradict the rules. Fixed: every row
  explanation is checked against its rule lines.
- Several fixed legal sentences were wrong or too broad (the three-year abandonment rule, "no hearing" above a
  use-size limit, the section cited when only late hours are prohibited). Corrected or narrowed.
- Where the use itself is prohibited, the health and entertainment rows said "allowed" or "further review".
  They now read "not permitted", because no City permit can issue then (Planning Code § 175(a)).
- The cut-down guard let reworded or empty "cuts" through. Tightened.

Left open: reports stored before this change are withheld as "earlier format", including ones already
unlocked, and re-running costs another credit. That matters only once this reaches production.

## 6. Tests

| Suite | Result |
|---|---|
| API (`ruff`, `ruff format --check`, `mypy`, `pytest`) | 1,169 passed, 1 skipped, 4 expected failures (the known gaps) |
| Records package | 186 passed, 9 skipped |
| Web lint and type check | clean |
| Web build and browser tests | reported by the fix agent: build succeeded, 26 passed. Not re-run by me |

## 7. Cost

| | |
|---|---|
| Five runs | $9.76 ($1.73 to $2.14 each, average $1.95) |
| Two runs cut off when the computer slept | about $1.00, estimated, not metered |
| Time per run | about 8 to 10 minutes |

A report now costs about $1.95, up from about $1.50 in Part 3. The increase is the extra checking: every row
explanation is an item, and each cut-down sentence is checked a second time. At this price 40 backtest reports
would cost about $78, against the $80 backtest cap, with no room for re-runs. The backtest plan has to deal
with that before it is approved.
