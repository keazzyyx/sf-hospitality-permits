# The intake model records only what the text states (decision of 2026-11-12)

## The decision

"Intake model: it may only record facts the text states. Anything it would infer becomes unknown and is named in
'Insufficient information'. Test it against the D22 mezzanine case."

## What changed

- The intake model must now quote the text for every fact the rules read. It sends `quotes`: a field and the
  exact words that state it.
- Code checks each quote (`apps/api/app/memo/stated.py`). The quote must be in the text, and its words must be
  able to state the value. "Ground-floor" states the first story. "A mezzanine" states no story. A number must be
  in the quote, with its unit. A closing time must follow a closing word ("until", "to", a dash). A "no" must be
  next to its own subject. A quote that hedges ("maybe live music") states no yes/no fact. A quote with "..." is
  read part by part, so words from two places cannot be joined into a new phrase.
- A value with no such quote is cleared. It becomes "not stated", the same as a fact the model left empty.
- The profile keeps a record of what was cleared (`intake_cleared`). An intake answer, a clarification answer or
  an override that gives the fact later takes it off the record, even when it gives the same value ("No
  alcohol").
- The report names each cleared fact. A row that needs it says "Insufficient information" and lists it. Any other
  cleared fact is asked in "What the rules could not establish": "Not known: <fact>. The description does not
  state it, so the report does not assume it."
- A cleared "yes" is not read as "no". If the model read alcohol, entertainment or an outdoor area that the text
  does not state, that row is added and says "Insufficient information". If it read a story the text does not
  state, the zoning use controls are not decided until the story is given.
- Later stages never see a removed guess. Their copy of the profile leaves out the removed values and the model's
  own assumptions.
- The memo's intake has its own prompt and tool. The checklist (`/v1/plans`) keeps its old prompt and tool,
  byte for byte, and runs no check, so nothing changes there.
- The facts only the applicant gives (`MODEL_MAY_NOT_SET`) are still cleared first. Temperature stays 0. The
  backtest sends the intake request the same way, with the new `quotes` field in its tool.
- The prompt's examples are new, general ones. None is taken from a backtest case.

## Checked against the 40 backtest texts (no model)

With every sentence of each text offered as a quote, every fact the two readers coded from the text is kept,
except one: D03's floor area. The readers added 1,100 and 1,200 square feet to get 2,300. The text never gives
2,300, so the check clears it. In that case the intake answer gives the floor area anyway.

## D22, end to end (one case, 2026-11-12)

Run: `python -m app.backtest.run --cases D22 --no-conditional --cap 2`, with a fresh journal and results directory
outside `backtest/results`. Cost: $0.8592 in 10 batches (cap $2.00).

| | Before (40-case run) | After |
|---|---|---|
| Stories on the profile | first, second | first (quote: "ground-floor") |
| Seats | 120 (guessed) | not stated |
| Change of use | true (guessed from "vacant") | cleared: the quote was "vacant", which does not state it |
| Zoning and use | Not permitted (false blocker) | Further review (as the record) |
| Health permit | Not permitted | Allowed |
| Building permit and change of use | Not permitted | Insufficient information: what the space was last used as; whether the space is for fewer than 50 people; the existing occupancy group |

The three statuses now match the rules-only run on the hand-entered facts. The model itself did not read the
mezzanine as a story this time; had it done so, the check would have dropped it (unit test
`test_d22_the_mezzanine_is_dropped_and_ground_floor_gives_the_first_story`).

This run used the first version of the check. The review fixes after it (above) were not re-run against the
model, to spend nothing more. They change the memo prompt a little: four checklist lines that invited guesses are
replaced. The fixes are covered by unit tests.

## Limits

- The check cannot tell a quoted word used in another sense (a quote of "a bar/restaurant" that names the old
  use, read as the new business). It catches values the quoted words cannot state.
- The yes/no fields of the older profile cannot hold "not stated", so a cleared one is stored as false. The
  rules do not read that false as "no": the profile's record of what was cleared tells them the fact is not
  known (see "What changed").
- A story that is not stated makes the use controls "not decided". If the first story already needs a
  conditional use, the zoning row stays "Further review" (a conditional use outranks "not decided"), and the
  story is named in the open questions as needed for zoning.
- A removed "no" (no entertainment, no outdoor area) is treated like a fact never mentioned: no row is added, and
  it is asked in the open questions.
