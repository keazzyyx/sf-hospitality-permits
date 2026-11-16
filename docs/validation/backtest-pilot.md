# Backtest pilot: what it found and what was fixed

Run 2026-11-11. Two cases, N09 (formula-retail limited restaurant, Irving Street; did not reach approval) and D02
(restaurant with a Type 47 licence, Columbus Avenue; approved), each end to end and conditional, through the Message
Batches API. Nothing was written to production and nothing was pushed to `main`.

## Cost

| Run | Requests | Batches | Cost |
|---|---|---|---|
| First pilot | 161 | 13 | $2.60 |
| Pilot rerun on the fixed code | 159 | 14 | $2.54 |
| A first attempt rejected by the API (no charge) | 2 | 1 | $0.00 |

About $1.27 per case for both runs, against the plan's $1.63. By stage, most of the cost goes to the writer (risk) and
the citation check (verify), as in the live runs.

## The review

Before the 38-case run, five independent reviewers went over the pilot's outputs and the harness, and each finding
was checked by a second agent asked to refute it. These were confirmed, and all are fixed.

**What the model could see from after the cut-off**

- Rule lines printed the end dates of controls that changed later ("§ 722, in force since before 2022-01-01 until
  2025-12-14"), and the North Beach district's name carried "(repealed 2025-12-15)". The model repeated them in the
  report. Fixed: in a backtest the rules read the dated controls as they could be known on the cut-off day (a later
  version is not there, the version in force has no known end, a later repeal note is removed). The only end date
  kept is the laundromat rule's, a three-year sunset written into the ordinance that created it, known from day one.
- A referral step's section label named the 2025 renumbering under Ordinance 118-25. Fixed the same way.
- Today's zoning and overlay summaries ("no separate North Beach alcohol SUD") went to the writer and the checker.
  Fixed: the district and overlays are named and drawn as on today's map; what they allow is what the dated rule
  lines say for the cut-off day.
- The records date and the ages of pending cases were measured to 2026-11-09, and the records stage's base-rate tool
  counted its window back from today. Fixed: both use the cut-off day.
- The permit catalogue carries dated rule changes ("Since August 2025 small businesses no longer need a permit … for
  sidewalk tables"). Fixed: sentences naming a day or month after the cut-off are taken out, in the writer's copy,
  the intake stage's copy, tool results and the checker's evidence; the block is labelled as November 2026 figures.
- The conditional run's supplied pathway quoted the case's outcome ("the Department later approved…"). Fixed: it
  states only the pathway and the triggers that require it.
- The leak guard had no motion number for six decided cases. Fixed: all 25 decided cases' motion numbers were read
  from the motion PDFs (`backtest/motions.json`).

Check: a scan of every prompt the data builds, for all 40 cases and both runs (`python -m app.backtest.scan`), finds
no date after the cut-off other than the laundromat sunset, and no case's own record, project or motion number. The
live runs also record any later date the model was sent (`leakage.json`, `later_dates_sent_to_the_model`).

**The harness**

- A restart would have paid again for every turn after the first in multi-turn stages (the request's hash changed
  when an earlier answer was rebuilt from the journal). Fixed; the conditional run also reads the end-to-end run's
  records and comparables from its saved stages, so it does not depend on replay.
- A large stage could exceed the $20-per-batch estimate; it is now split into several batches under the limit, and the
  cap is checked for the whole flush before anything is sent. The cap is a total for the whole backtest (earlier
  spend in the journal counts).
- Transient errors while waiting for a batch no longer lose it; a crashed run's paid batches are recovered on restart;
  an account error keeps the paid answers before stopping; the SDK no longer retries a batch create (which could pay
  twice).
- A run whose citation check did not run, or ran in part, is marked so.

**The scoring**

- "Unsupported" now counts sentences the checker found unsupported outright, separately from partly supported
  sentences whose cut failed.
- Every missing-input phrase maps to a fact (the scorer stops if one does not).
- The intake model's assumptions are listed per case, and triggers raised outside the inventory are counted.
- In the conditional runs the pathway is shown as supplied, not as a result.
- The trigger comparison follows the coverage script ("different control" is its own result).
- The licences of unknown status: the group is 9 cases (10 licences) where a licence on the case's own parcel or
  address has an unknown status on the cut-off day; the sensitivity check compares every trigger and missing input,
  not only row statuses.

## Found and not changed

- **N09's health row reads "Allowed" while zoning reads "Not permitted".** The rule that no City permit can issue for
  a prohibited use (Planning Code § 175(a)) is applied to the use-control triggers, not to the formula-retail
  prohibition, although the alcohol row honours it. A product rule question; not changed during the backtest.
- **The citation check does not show a finding the rule lines of its row** (only a row summary gets them), so a
  sentence that correctly restates a rule line can be cut as "not in the records". Not changed during the backtest;
  the results report how many cut or removed sentences only restated the rule lines (a Haiku comparison, under $2).
- **The intake temperature.** Left as it is: the rules still read what the intake model fills in (business type, what
  is poured, closing time, entertainment), and temperature 0 is what kept the five 995 Valencia profiles identical.
  Intake requests that set it go in their own batch on the API version that accepts it.
