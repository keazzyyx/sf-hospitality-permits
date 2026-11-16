# Claude API spend ledger

Every Claude API run made for validation work, with its real token counts.

Prices used ($ per million tokens, prompts under 100K): Claude Haiku 5.5 $0.10 input / $0.50 output; Claude
Sonnet 4.5 (the report's production model) $3.00 input / $15.00 output. Batch API
halves both; cache writes cost 1.25x input and cache reads 0.1x input.

## Ledger

| Date | What ran | Model | API | Input tokens | Output tokens | Cost | Running total |
|---|---|---|---|---|---|---|---|
| 2026-11-09 | Hospitality classifier, 50-record trial | claude-haiku-5-5 | Messages (standard) | 8,776 | 1,353 | $0.0016 | $0.0016 |
| 2026-11-09 | Hospitality classifier, all 26,510 Planning records (1,059 requests) | claude-haiku-5-5 | Messages (standard) | 3,230,399 | 722,214 | $0.6841 | $0.6857 |
| 2026-11-10 | Full-conditions motion pass, 174 cases (regex extraction, no model calls) | — | — | 0 | 0 | $0.00 | $0.6857 |
| 2026-11-10 | Record classifier v2 (premises, use class, record kind): one trial request | claude-haiku-5-5 | Messages (standard) | 1,908 + 2,289 cache write | 985 | $0.0010 | $0.6867 |
| 2026-11-10 | Record classifier v2, all 26,510 Planning records (1,061 requests, batch msgbatch_removed_65) | claude-haiku-5-5 | Message Batches, prompt cached | 2,272,604 + 2,416 cache write + 2,560,960 cache read | 1,204,426 | $0.4277 | $1.1144 |
| 2026-11-10 | Motion lookup for 28 newly included cases; 20-motion hand check; Step 3 source research (no API-key model calls) | — | — | 0 | 0 | $0.00 | $1.1144 |
| 2026-11-10 | Part 3: 995 Valencia report, local database, run 1 (8 calls; first citation check) | claude-sonnet-4-5 | Messages (standard), prompt cached | 182,401 + 38,335 cache write + 24,339 cache read | 18,030 | $0.9687 | $2.0831 |
| 2026-11-10 | Part 3: 995 Valencia report, run 2 (stricter citation check) | claude-sonnet-4-5 | Messages (standard), prompt cached | 178,926 + 38,711 cache write + 24,339 cache read | 19,049 | $0.9750 | $3.0581 |
| 2026-11-10 | Part 3: 995 Valencia report, run 3 (length limits stated; 11 calls: the risk and check stages each retried) | claude-sonnet-4-5 | Messages (standard), prompt cached | 278,924 + 38,723 cache write + 43,211 cache read | 32,884 | $1.4882 | $4.5463 |
| 2026-11-10 | Part 3: 995 Valencia report, run 4 (9 calls; row summaries checked) | claude-sonnet-4-5 | Messages (standard), prompt cached | 231,844 + 39,085 cache write + 33,791 cache read | 22,241 | $1.1859 | $5.7322 |
| 2026-11-10 | Part 3: building and reviewing the new format; hand check of the citation checker (no API-key model calls) | — | — | 0 | 0 | $0.00 | $5.7322 |
| 2026-11-10 | Part 3: citation checker re-run on run 4's 39 sentences, batches of 5 (8 calls) | claude-sonnet-4-5 | Messages (standard), prompt cached | 30,309 + 6,988 cache write + 6,988 cache read | 3,272 | $0.1683 | $5.9005 |
| 2026-11-10 | Part 3: citation checker re-run, one sentence per call (39 calls) | claude-sonnet-4-5 | Messages (standard), prompt cached | 52,163 + 68,133 cache read | 5,422 | $0.2583 | $6.1588 |
| 2026-11-10 | Part 3: 995 Valencia report, run 5, the final example (49 calls: 42 of them the per-sentence check) | claude-sonnet-4-5 | Messages (standard), prompt cached | 226,167 + 47,774 cache write + 86,025 cache read | 42,464 | $1.5204 | $7.6792 |
| 2026-11-10 | Fixes 1 and 2: 995 Valencia report on the rule-set statuses, run 1 of 5 (81 calls; every row explanation checked, cut-down sentences re-checked) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 263,600 + 37,614 cache write + 210,263 cache read | 67,294 | $2.0043 | $9.6835 |
| 2026-11-10 | Fixes 1 and 2: 995 Valencia report on the rule-set statuses, run 2 of 5 (70 calls; every row explanation checked, cut-down sentences re-checked) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 322,623 + 40,118 cache write + 192,938 cache read | 58,715 | $2.0569 | $11.7404 |
| 2026-11-10 | Fixes 1 and 2: 995 Valencia report on the rule-set statuses, run 3 of 5 (70 calls; every row explanation checked, cut-down sentences re-checked) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 237,279 + 54,968 cache write + 159,956 cache read | 57,639 | $1.8305 | $13.5709 |
| 2026-11-10 | Fixes 1 and 2: 995 Valencia report on the rule-set statuses, run 4 of 5 (64 calls; every row explanation checked, cut-down sentences re-checked) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 254,491 + 20,858 cache write + 190,672 cache read | 55,275 | $1.7280 | $15.2989 |
| 2026-11-10 | Fixes 1 and 2: 995 Valencia report on the rule-set statuses, run 5 of 5 (69 calls; every row explanation checked, cut-down sentences re-checked) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 321,121 + 54,968 cache write + 169,885 cache read | 61,489 | $2.1428 | $17.4417 |
| 2026-11-10 | Fixes 1 and 2: two runs cut off when the computer slept (read timeout during the comparables stage; no usage file written). ESTIMATE, not metered: at most about $0.50 each | claude-sonnet-4-5 | Messages (standard), prompt cached | not metered | not metered | about $1.00 | about $18.44 |
| 2026-11-11 | 995 Valencia report, rule table v2, first five runs at once (before the intake model was barred from chain status and occupant count), run 1 (66 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 356,202 + 12,073 cache write + 230,074 cache read | 65,108 | $2.1595 | about $20.60 |
| 2026-11-11 | 995 Valencia report, rule table v2, first five runs at once (before the intake model was barred from chain status and occupant count), run 2 (68 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 246,899 + 28,795 cache write + 201,478 cache read | 61,406 | $1.8302 | about $22.43 |
| 2026-11-11 | 995 Valencia report, rule table v2, first five runs at once (before the intake model was barred from chain status and occupant count), run 3 (61 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 326,800 + 31,670 cache write + 191,042 cache read | 56,455 | $2.0033 | about $24.43 |
| 2026-11-11 | 995 Valencia report, rule table v2, first five runs at once (before the intake model was barred from chain status and occupant count), run 4 (61 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 313,858 + 21,308 cache write + 201,404 cache read | 53,880 | $1.8901 | about $26.32 |
| 2026-11-11 | 995 Valencia report, rule table v2, first five runs at once (before the intake model was barred from chain status and occupant count), run 5 (67 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 373,128 + 12,073 cache write + 232,861 cache read | 68,926 | $2.2684 | about $28.59 |
| 2026-11-11 | 995 Valencia report, rule table v2, final code, five runs at once, run 1 (61 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 272,235 + 47,543 cache write + 167,872 cache read | 54,868 | $1.8684 | about $30.46 |
| 2026-11-11 | 995 Valencia report, rule table v2, final code, five runs at once, run 2 (56 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 345,497 + 22,534 cache write + 188,134 cache read | 55,209 | $2.0056 | about $32.47 |
| 2026-11-11 | 995 Valencia report, rule table v2, final code, five runs at once, run 3 (57 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 314,835 + 29,029 cache write + 176,186 cache read | 57,399 | $1.9672 | about $34.43 |
| 2026-11-11 | 995 Valencia report, rule table v2, final code, five runs at once, run 4 (63 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 316,495 + 11,507 cache write + 223,222 cache read | 58,115 | $1.9313 | about $36.36 |
| 2026-11-11 | 995 Valencia report, rule table v2, final code, five runs at once, run 5 (66 calls) | claude-sonnet-4-5-20250929 | Messages (standard), prompt cached | 292,598 + 31,769 cache write + 203,081 cache read | 57,580 | $1.9216 | about $38.29 |
| 2026-11-11 | Backtest pilot, first attempt: the 2 intake requests were rejected by the Batches API (a field the SDK adds for the temperature); rejected requests are not billed. Stopped before the conditional half | claude-sonnet-4-5-20250929 | Message Batches | 0 billed | 0 | $0.00 | about $38.29 |
| 2026-11-11 | Backtest pilot: N09 and D02, end to end and conditional (161 requests in 13 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 855,572 + 31,816 cache write + 533,499 cache read | 152,270 | $2.6009 | about $40.89 |
| 2026-11-11 | Backtest pilot rerun after the pilot review's fixes: N09 and D02, end to end and conditional (159 requests in 14 batches; intake answered from the journal) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 842,883 + 31,162 cache write + 521,095 cache read | 147,633 | $2.5432 | about $43.43 |
| 2026-11-12 | Backtest main run, end to end: all 40 cases (D10 failed in the comparables stage: no structured result in 8 turns) (1954 requests in 13 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 11,470,005 + 51,351 cache write + 7,385,426 cache read | 1,839,145 | $32.2605 | about $75.69 |
| 2026-11-12 | Backtest: D10 end to end re-run fresh (own journal) after its failure (46 requests in 9 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 283,267 + 0 cache write + 174,127 cache read | 37,553 | $0.7327 | about $76.42 |
| 2026-11-12 | Backtest main run, conditional: 39 cases (correct pathway supplied; records and comparables reused) (1751 requests in 6 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 6,851,279 + 0 cache write + 5,301,873 cache read | 1,552,493 | $22.7159 | about $99.14 |
| 2026-11-12 | Backtest: D10 conditional (66 requests in 4 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 238,597 + 0 cache write + 196,722 cache read | 59,546 | $0.8340 | about $99.97 |
| 2026-11-12 | Backtest scoring: which cut or removed sentences only restate the rule lines (2066 sentences, one request each) | claude-haiku-4-5 | Message Batches (half price), prompt cached | see journal-restatements.jsonl | | $1.6757 | about $101.65 |
| 2026-11-12 | Citation check decision: the check alone re-run with each finding's rule lines, on N14 and D02 end to end (the 21 cut sentences that only restated rule lines, plus 10 cut sentences that did not, as a control; 40 requests in 4 batches, re-checks included; cap $1.00) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached | see journal-verify-recheck.jsonl (batches below) | | $0.4164 | about $102.07 |
| 2026-11-12 | Intake decision (stated facts only): D22 end to end, fresh journal, cap $2 (43 requests in 10 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 269,754 + 42,934 cache write + 130,414 cache read | 40,821 | $0.8592 | about $102.93 |
| 2026-11-12 | Smoke test, by mistake: a local 995 Valencia report run on the old code (writer chain) from a worktree, stopped after about 10.5 minutes, before its cost printed. Not metered; estimated from the five metered runs of the same report on 2026-11-11 (range about $0.90 to $2.30). Over the task's $1.00 cap. | claude-sonnet-4-5-20250929 | Messages API (not batched) | not metered | | about $1.90 (estimate) | about $104.83 |
| 2026-11-12 | Pre-release smoke test: one real local report on the merged code (995 Valencia wine bar; intake is the only model call; 2 requests) | claude-sonnet-4-5-20250929 | Messages API, prompt cached | 5,975 + 11,926 cache write + 11,926 cache read | 2,006 | $0.0963 | about $104.93 |
| 2026-11-12 | Holdout run: the 20 frozen cases on the rule-fix branch, report without the writer (intake only; 3 batches) | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached | see journal-holdout.jsonl | | $0.3883 | about $105.32 |
| 2026-11-13 | 2010-2018 conditions-page review, stage 1 submitted (reader + checker, 291 motions, 582 requests, batch msgbatch_removed_66, cap $15.00); worst case $0.79, expected $0.14, billed on collect | claude-haiku-5-5 | Message Batches (half price), prompt cached (one-hour) | expected 2,814,990 | expected 232,800 | $0.00 (metered on collect) | about $105.32 |
| 2026-11-13 | 2010-2018 conditions-page review, stage 1 (reader + checker) collected: 582 answers, 0 failed (batch msgbatch_removed_66) | claude-haiku-5-5 | Message Batches (half price), prompt cached (one-hour) | 1,541,808 + 2,951 cache write + 1,615,591 cache read | 109,925 | $0.1129 | about $105.43 |
| 2026-11-13 | 2010-2018 conditions-page review, stage 2 submitted (Opus on 5 disagreements, batch msgbatch_removed_67, cap $15.00 for the whole review); worst case $0.64, expected $0.09, billed on collect | claude-opus-5-5 | Message Batches (half price), prompt cached (one-hour) | expected 26,361 | expected 5,000 | $0.00 (metered on collect) | about $105.43 |
| 2026-11-13 | 2010-2018 conditions-page review, stage 2 (Opus on the disagreements) collected: 5 answers, 0 failed (batch msgbatch_removed_67) | claude-opus-5-5 | Message Batches (half price), prompt cached (one-hour) | 15,607 + 2,831 cache write + 11,324 cache read | 1,002 | $0.0537 | about $105.48 |
| 2026-11-15 | Patch review, step 5: one local 2301 Chestnut St report, first intake (chain no, 6,000 sq ft, new licence), before the quote-recording wrapper (logged late, 2026-11-16) | claude-sonnet-4-5-20250929 | Messages API, prompt cached | 2,063 + 11,926 cache write | 1,317 | $0.0707 | about $105.55 |
| 2026-11-15 | Patch review, step 5: the same report again with the wrapper recording the intake quotes (logged late, 2026-11-16) | claude-sonnet-4-5-20250929 | Messages API, prompt cached | see scratchpad chestnut/u1 | | $0.0288 | about $105.58 |
| 2026-11-15 | Patch review, step 5: the second report (stories, alcohol served, last use, fewer than 50 people, outdoor area added; logged late, 2026-11-16) | claude-sonnet-4-5-20250929 | Messages API, prompt cached | see scratchpad chestnut/u2 | | $0.0283 | about $105.61 |

Backtest total (pilot, rerun, main run, re-run of D10, restatement check): about $63.36 of the $80 backtest cap. Validation total: about $105.61 of $130, including the three 2026-11-15 rows logged late. (The citation-check re-run, the D22 intake test and the smoke-test overspend of 2026-11-12 are outside the backtest cap; the smoke-test figure is an estimate.)

Notes:
- The citation-check re-run of 2026-11-12 is in `$LOCAL_DATA_DIR/backtest/journal-verify-recheck.jsonl`, next to
  the other backtest journals (40 lines; its own total reads $0.4164). Its four batches:
  N14 `msgbatch_removed_68` (18 requests, $0.2052) and `msgbatch_removed_69` (4, $0.0411);
  D02 `msgbatch_removed_70` (13, $0.1274) and `msgbatch_removed_71` (5, $0.0427).
- The classifier ran before the batch rule. Through the Batches API it would have cost about $0.34. Its system
  prompt was under the minimum cacheable length, so caching did not apply.
- The v2 classifier went through the Batches API with a cached system prompt: 53% of its input tokens were
  cache reads. At standard prices without caching the same job would have cost about $1.09.
- Not counted here: Claude Code's own subagents (they do not use the API key), and memos run on the live site.

## Cycle from 2026-11-16

The cycle reset at 2026-11-16 00:00 UTC, so the running total starts again from zero. From this cycle accuracy
comes first, not cost: the $20 single-run line and the per-task caps are dropped, the strongest model is used
wherever it improves accuracy, with independent double-checks on anything that feeds the validation numbers,
and a single job estimated over $50 is reviewed before it runs. The $200 monthly balance is shared with the
live site.

| Date | What ran | Model | API | Input tokens | Output tokens | Cost | Running total (this cycle) |
|---|---|---|---|---|---|---|---|
| 2026-11-16 | Headline check: one local 2301 Chestnut St report on the merged branch (22501ef), intake chain no / 6,000 sq ft / new licence. A first attempt the same minute crashed after its intake call (a missing setting in the wrapper), so it was billed but not metered: estimate from the metered run | claude-sonnet-4-5-20250929 | Messages API, prompt cached | about 2,063 + 11,926 cache read | about 1,337 | about $0.03 (estimate) | about $0.03 |
| 2026-11-16 | Headline check: the same report, metered (scratchpad chestnut/hu1.json) | claude-sonnet-4-5-20250929 | Messages API, prompt cached | 2,063 + 11,926 cache read | 1,337 | $0.0298 | about $0.06 |
| 2026-11-16 | Holdout re-run, ABC licence arms: the 20 frozen cases at 22501ef (spelling-and-intake-questions, no rule changes, harness b-holdout-rerun 448d260), report without the writer, intake model = product's (24 requests, 3 batches msgbatch_removed_03, msgbatch_removed_04, msgbatch_removed_05; journal scratchpad holdout/journal-holdout-sonnet.jsonl); the ARM 94110 run replayed all 24 answers from the journal at $0 | claude-sonnet-4-5-20250929 | Message Batches (half price), prompt cached (one-hour) | 52,911 + 23,718 cache write + 260,578 cache read | 25,885 | $0.3837 | about $0.44 |
| 2026-11-16 | Holdout re-run, strongest-model intake arm: the same 20 cases and code, intake model Opus 5.5 (no temperature, tool_choice auto, API default effort; 21 requests, 2 batches msgbatch_removed_01, msgbatch_removed_02; journal scratchpad holdout/journal-holdout-opus.jsonl); the ARM 94110 run replayed all 21 answers at $0 | claude-opus-5-5 | Message Batches (half price), prompt cached (one-hour) | 55,510 + 32,787 cache write + 311,011 cache read | 27,059 (thinking included) | $0.5439 | about $0.99 |
| 2026-11-16 | Post-deploy check: one 2301 Chestnut St report at 59e41bb (main) against the production precedent store after the ABC load, read only (client-side guard: 0 statements refused), intake chain no / 6,000 sq ft / new licence (scratchpad chestnut/live-usage.json) | claude-sonnet-4-5-20250929 | Messages API, prompt cached (cache written, not read) | 2,063 + 11,926 cache write | 1,318 | $0.0707 | about $1.06 |

Not counted here: Claude Code's own subagents (the reviews and re-checks of 2026-11-16 ran as subagents and do not use the API key), and memos run on the live site.
