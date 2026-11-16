# Part 3: the new report format

Built and run 2026-11-10. Everything ran locally: the report was generated against the local copy of the records
(`$LOCAL_DATA_DIR`, which carries the Step 2 labels and motion conditions), with the production models, and
nothing was written to production or pushed to `main`.

Example report: [`part3/memo-995-valencia.pdf`](part3/memo-995-valencia.pdf) and
[`part3/memo-995-valencia.json`](part3/memo-995-valencia.json) (995 Valencia St, "40-seat wine bar, small kitchen,
open until 1am, occasional live music"). It is run 5 below. Earlier runs are kept beside it as `run1-…` to
`run4-…`, with what the checker was shown and its raw verdicts.

## 1. What changed

The Likely / Conditional / Unlikely verdict and the narrative are gone. A report is now:

| Part | What it is |
|---|---|
| Approval rows | One row per approval the concept needs: zoning and use, alcohol licence, entertainment permit, health permit, building permit and change of use, outdoor. A row appears only when the concept needs it. |
| Status | Each row has one of five statuses: Allowed, Further review, Potential blocker, Not permitted, Insufficient information. The definitions are in the schema and are printed into the prompt from the schema, so they cannot drift apart. |
| Evidence label | Every finding, expected condition and filing step is labelled Verified, Likely applicable, Needs confirmation or Professional review required. Verified and Likely applicable must cite a record. |
| Overall line and next step | One line across the rows and one recommended next step. The overall status is computed: it is the most serious row status. |
| Could not establish | What the records cannot show, grouped by what would settle it: plans, an inspection, the applicant's history, an agency's answer. |
| Site history | Every record on file at the address or parcel, newest first, with its kind. Building work is listed here and is kept out of the comparables and the counts. |
| Comparables as evidence | Outcome, conditions, days to decision, the source and the record kind, and a note on what each source leaves out. |
| Counts, not rates | See section 3. |
| Citation check | A second pass reads each cited sentence against the full text of its cited records. See section 4. |
| "No outcome history for this pathway yet." | Printed on the alcohol and entertainment rows. |

Old reports stored in the previous format still open: they show an "earlier report format" card with a re-run
link, and unlocking one is refused before a credit is spent.

## 2. The 995 Valencia report

| Approval | Status | Why, in one line |
|---|---|---|
| Zoning and use | Further review | A bar needs a Conditional Use Authorization and a hearing. |
| Alcohol licence | Potential blocker | The Mission alcohol district requires a licence transferred from another bar inside the district. "No outcome history for this pathway yet." |
| Entertainment permit | Further review | Live music until 1 a.m. needs a Place of Entertainment permit and a hearing. "No outcome history for this pathway yet." |
| Health permit | Allowed | Plan check, inspection and a permit to operate. |
| Building permit and change of use | Allowed | Tenant improvements need a building permit. See the gap on change of use in section 5. |

Overall: **Potential blocker.** Next step: confirm with Planning that a bar licence is available for transfer
inside the Mission alcohol district, then pre-file the Conditional Use application.

Of its 42 cited sentences, 21 kept their label and 21 were downgraded by the check; none were dropped and no
row lost its status. All five row summaries carry a checker note.

- **Site history:** 9 records at the address or parcel: 2 ABC licences, 2 use decisions, 5 agency referrals. One
  licence and one use decision are for 999 Valencia on the same parcel and are marked "Filed under 999 Valencia St".
  No building-work record exists for this parcel, so the "kitchen hood" case does not arise here. Tests cover it:
  a labelled building-work record at the address appears in the site history and never among the comparables or
  in the counts.
- **Counts:** "1 approved / 0 denied / 2 withdrawn. N = 3 dated decisions within 1,000 ft, last 10 years; too few
  for a rate; left out: 74 permits and licences, 321 records that are not use decisions for this kind of business."
- **Comparables:** 10 (4 use decisions, 3 agency referrals, 3 Entertainment Commission permits).

The old report on the same address gave a "Conditional" verdict. With the labels applied, only three dated use
decisions for this kind of business sit within 1,000 ft in ten years, and two of them were withdrawn.

## 3. The counting rule, as built

- A rate is printed only when **N is 10 or more** dated comparables with known outcomes. Below that the report
  prints the counts and "too few for a rate". N is always printed.
- The pool never contains permits and licences on file (ABC licences, Entertainment Commission permits): a list
  of grants cannot show a failure. It never contains a row without both a filing date and a decision date, or
  one decided before it was filed.
- Where records carry the Step 2 labels, the pool is only **use decisions about a food, drink or entertainment
  premises**. Agency referrals can appear among the comparables but are not counted. Building work and other
  records appear only in the site history.
- Every left-out group is counted and shown.
- Production records carry no labels yet. Until they do, the label rules fall back to the old behaviour there;
  the date and grant-only rules apply everywhere.

## 4. The citation check, and how well it works

I ran the report five times while tightening the check, and measured the check by hand after run 4.

| Run | Check | Sentences checked | Kept as labelled | Downgraded | Dropped | Cost | Time |
|---|---|---|---|---|---|---|---|
| 1 | First version, one call for all sentences | 38 | 38 | 0 | 0 | $0.97 | 6.3 min |
| 2 | Checker must list what the records do not state before giving a verdict | 40 | 35 | 5 | 0 | $0.98 | 6.9 min |
| 3 | + length limits stated in the prompt | 41 | 28 | 13 | 0 | $1.49 | 12.6 min |
| 4 | + row summaries checked; advice in filing steps not treated as a claim | 39 | 25 | 14 | 0 | $1.19 | 8.1 min |
| 5 (final) | + one sentence per call | 42 | 21 | 21 | 0 | $1.52 | 7.5 min |

Run 1 passed every sentence. Reading it myself, about 9 of its 23 findings joined a real record to a conclusion
the record does not state ("…demonstrating historical willingness to approve…"), and one called an agency
referral a building permit. That is why the check was rewritten.

**Hand check of run 4.** Two readers graded all 39 checked sentences separately against the exact records the
checker was shown, without seeing its verdicts; a third reader settled the 17 where anyone differed. The standard
is strict: a conclusion counts as part of the sentence, and it is supported only if a cited record states it.

| Run 4's 39 sentences | Hand check: should be flagged | Hand check: fully supported |
|---|---|---|
| Checker flagged | 19 | 1 |
| Checker passed | **12** | 7 |

- The checker's flags were right 19 times out of 20.
- It **missed 12 of the 31 sentences that should have been flagged** (it caught 61%). Five of the twelve were
  findings that stayed labelled Verified. Examples: "DPH approved…" where the record is Planning's answer to a
  DPH referral; a code section named in the sentence that the cited record never mentions; "neighborhood
  notification per §312" cited to a record that does not mention notification.
- The two readers agreed with each other on 37 of 39.

**The fix: one sentence per call.** I re-ran only the checker on the same 39 sentences and scored it against the
same hand check:

| Checker set-up | Caught of 31 | Wrong flags | Cost for the 39 sentences |
|---|---|---|---|
| One call for all sentences (as run 4) | 19 (61%) | 1 | part of the run |
| Batches of five | 18 (58%) | 2 | $0.17 |
| **One sentence per call** | **27 (87%)** | 4 | $0.26 |

The report now checks one sentence per call, up to six at a time. The final example (run 5) was generated that
way: the check took 1 minute 45 seconds and flagged 35 of its 42 sentences, against 20 of 39 in run 4. I did not
hand-check run 5; the 87% figure is from the re-run on run 4's sentences.

What a flag does: a Verified sentence that is only partly supported becomes Likely applicable and shows the
checker's note; a sentence the records do not support at all loses its citation and becomes Needs confirmation
(a finding) or is removed (an expected condition or filing step); a row whose status has lost its support falls
back to Insufficient information.

## 5. Known gaps

- **The check still misses about 1 flag in 8** on this sample of 39 sentences from one report. It is a filter,
  not a guarantee, and the sample is small.
- **The writer still over-claims.** Even with the stricter prompt, a third to a half of cited sentences are
  downgraded on each run. The check is doing work the writing stage should not leave for it.
- **Text the check does not cover:** the comparables' takeaways and "why comparable" lines (the PDF marks them
  "agent-written, not checked"; the web page does not show them), the records summary, the concept summary, the
  next step, and the could-not-establish questions. The first three are filtered for opposition speculation; the
  rest rely on the prompt rule alone.
- **Opposition** is not reported anywhere, per the Step 2 instruction; the flag stays off until its extraction
  is right 27 times out of 30.
- **Reports vary run to run.** Same address, same concept, same records: in run 4 the zoning row was "Potential
  blocker" and the alcohol row "Further review"; in the other four runs it was the other way round. The overall
  status was "Potential blocker" every time.
- **Change of use is inconsistent.** The final report's building row says "no change of use is assumed" and is
  marked Allowed, while its zoning row says the bar needs a Conditional Use Authorization. Runs 3 and 4 said the
  opposite (restaurant to bar is a change of use, Further review); runs 1 and 2 said Allowed. The intake step records "no change of use"
  when the last tenant served food, and the writer sometimes follows it despite the prompt rule. The checker
  flagged the summary ("records do not state the assumption about no change of use") but a partly supported
  summary is kept with its note, not removed.
- **Slower and dearer.** A report now takes 7 to 13 minutes and $1.00 to $1.50 in model cost, of which the
  per-sentence check is roughly $0.25 to $0.35; the old one took about 7 minutes.
- **"Occasional live music"** is read as needing a full Place of Entertainment permit. A Limited Live
  Performance permit may fit better; the report does not weigh the two.
- **Site history** depends on parcel and address matching. Records with no map point are not found.
- **Nothing here is on production.** Production records have no labels, so the site history there would show
  kinds as "Not labelled" and the counts would use the older pool.

## 6. Tests

| Suite | Result |
|---|---|
| API (`ruff`, `ruff format --check`, `mypy`, `pytest`) | 657 passed |
| Records package (`pytest`) | 186 passed, 9 skipped |
| Web (`lint`, `typecheck`, `build`, Playwright) | 24 passed |

## 7. Cost

Five report runs ($6.14) and two checker re-runs ($0.43) are in [`spend.md`](spend.md): $6.57 for Part 3.
Building and reviewing the format and the hand check used no API-key calls.
