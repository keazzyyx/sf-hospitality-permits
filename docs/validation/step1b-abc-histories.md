# Step 1b: ABC application histories from the archived daily reports

Run 2026-11-10 on the full archive, 2019-01-01 to 2026-11-09 (2,533 days of Status Changes, 2,233 of Issued
Licenses, 767 of New Applications; 128,933 file numbers). Everything is local: nothing was written to production
and no ABC page was requested for this step beyond the backfill itself.

Counts are files (licence numbers), never report rows. Scripts: `scripts/validation/abc_histories.py` and
`abc_workload.py`. Full numbers: [`abc-histories.json`](abc-histories.json).

## 1. What the three reports actually show

My first pass was far off ABC's own figures (approvals 12% to 55% under, withdrawals 2 to 3 times over). The
cause was how I read the reports. Two independent checks, working from the raw files without the script, tested
the reading below and corrected two parts of my own first correction.

| Report | What it shows | Evidence |
|---|---|---|
| Status Changes | Each record's **most recent** transition as of the day the page was fetched, listed on **every** date the record changed. Not the change made on the report's date. | Of 138,691 pairs of consecutive dates for a file, 147 chain (one ends where the next begins) and 138,544 do not. Rows on 2019 to 2022 dates carry 2026 and 2027 expiry dates in 100% of cases. |
| Issued Licences | Each licence's status **today**, not when issued. Every row is an issue, except licence type 30, which is a 120-day temporary permit. | The share of files reading Active rises from 44% on 2019 dates to 86% on 2025 dates. 98.7% to 99.7% of Active rows are active in today's export, every year. |
| New Applications | For a past date, only the applications **still pending today**. Not what was filed that day. | 5,169 rows over 767 days. |

What follows for a file's dates:

- **Never issued (withdrawn or denied):** the first date is the filing, the last is the withdrawal or denial.
  Checked three ways: first dates run in file-number order (rank correlation 0.994); the two dates are a median
  101 days apart; 1,323 of the 1,327 files with only one date carry file numbers from before the archive starts.
- **Issued:** the report carries **no filing date**. The two dates are the issue day and the next business day.
  I had read the first as the filing; that is wrong (it would mean 99% of new licences issued within 30 days of
  filing, which the 30-day posting rule forbids).
- **Filing date of an issued file:** estimated from its file number, and labelled "estimated" everywhere. File
  numbers are handed out in filing order: the estimate is off by a median of 0 days (p90 0.5 days, N = 12,569),
  and by a median of 0 days (p90 1.5) on 208 issued files whose filing date is known another way. With it, no
  retail original issues in under 30 days (median 126 days).

## 2. The check against ABC's Annual Workload Summaries

ABC's pages give, per fiscal year, a statewide Licensing table and two tables of application investigations by
office. The pages define none of the rows in words; what a row counts is inferred from the arithmetic.

### Statewide (ours / ABC, gap)

| Fiscal year | Permanent licences issued | Withdrawn, not priority-drawing entries | General-type originals filed vs priority applications received |
|---|---|---|---|
| 2019-20 | 8,366 / 8,700 (-3.8%) | 953 / 952 (+0.1%) | 1,357 / 1,380 (-1.7%) |
| 2020-21 | 7,154 / 7,261 (-1.5%) | 799 / 820 (-2.6%) | 1,374 / 1,381 (-0.5%) |
| 2021-22 | 8,821 / 9,104 (-3.1%) | **796 / 913 (-12.8%)** | 1,396 / 1,401 (-0.4%) |
| 2022-23 | 8,410 / 8,738 (-3.8%) | 845 / 865 (-2.3%) | 1,179 / 1,166 (+1.1%) |
| 2023-24 | 8,264 / 8,542 (-3.3%) | 845 / 883 (-4.3%) | 1,197 / 1,184 (+1.1%) |
| 2024-25 | 8,117 / 8,424 (-3.6%) | **856 / 907 (-5.6%)** | 1,054 / 1,034 (+1.9%) |
| 2025-26 | 7,411 / 7,730 (-4.1%) | 910 / 950 (-4.2%) | 1,241 / 1,222 (+1.6%) |

I recounted the withdrawal column myself from the raw files with a separate script: 947 / 796 / 787 / 837 / 839 /
856 / 903, within 1% of the script in every year.

### The withdrawal gap, explained

- **Why my first number was 2 to 3 times ABC's.** Each withdrawn application appears twice in Status Changes, on
  its filing date and on its withdrawal date, both reading "PEND to WITHDRAWN". I had counted both. Counting each
  file once, on its last date, removes that.
- **Why it was still about 60% over.** About 800 to 1,000 of each year's withdrawals are **priority-drawing
  entries**. A new general licence (types 21, 47, 48) can only be had through ABC's yearly drawing; entries that
  are not drawn are withdrawn. ABC counts these apart from permanent applications ("Priority License Applications
  Received"), so they are not in its "Applications Withdrawn".
- **The rule used to separate them**, and why it is not tuned to the answer: a never-issued original of type 21,
  47 or 48. It is checked against a different ABC figure from the one being explained: such files, counted by
  filing year, are within -1.7% to +1.9% of ABC's priority applications received in all seven years.
- **Result:** within 5% of ABC in five of seven years, at or below ABC in six.
- **Still over 5%:**
  - **FY2021-22, -12.8%: unexplained.** The shortfall is spread across offices, not one event. ABC itself
    restated that year from 913 to 883 on a later page (-9.9% against the restated figure).
  - **FY2024-25, -5.6%.**
- **Known reasons we run a few per cent low**, none applied because each would need a cut-off chosen against
  ABC's totals:
  - A drawing winner who withdraws later is an ordinary withdrawal to ABC but a priority entry here (22 to 59
    files a year withdrawn 12 or more months after filing).
  - A withdrawal that was later reversed is invisible, because only the latest transition survives (241 files).

### Other statewide gaps

- **Issued licences are 1.5% to 4.1% under ABC's "Permanent Licenses Issued"** every year. About 1.3 points is
  ABC counting a duplicate licence number once per number where a file counts once here. The rest is unexplained.
- **The figure quoted for FY2025-26, 7,991 approved, is "Applications Recommended for Approval"**
  (investigations), not licences issued. ABC's own issued figure is 1.8% to 6.1% below it every year. Ours is
  5.4% to 9.0% below it.
- **Original against transfer.** ABC counts premises transfers with originals. Grouped that way, original
  investigations are within -5.6% to +0.2%. Person-to-person transfers stay 6.9% to 15.6% under ABC:
  unexplained (an approved transfer with no issue in the year is not visible in these reports).
- **Denied.** Files reading "PEND to DENIED", by fiscal year: 3, 6, 8, 12, 4, 14, 32, against ABC's
  "Recommended for Denial" of 5, 4, 13, 14, 10, 23, 30. These are different things (a recommendation against a
  final status) and the numbers are too small for a percentage.

### San Francisco office (district code 24)

| Fiscal year | Issued vs approved investigations | Withdrawn, not priority vs withdrawn |
|---|---|---|
| 2019-20 | 374 / 536 (-30.2%) | 54 / 51 |
| 2020-21 | 258 / 272 (-5.1%) | 27 / 23 |
| 2021-22 | 349 / 383 (-8.9%) | 28 / 25 |
| 2022-23 | 329 / 342 (-3.8%) | 37 / 33 |
| 2023-24 | 329 / 360 (-8.6%) | 31 / 30 |
| 2024-25 | 341 / 363 (-6.1%) | 24 / 19 |
| 2025-26 | 282 / 313 (-9.9%) | 41 / 45 |

- **FY2019-20, -30%: explained.** The San Francisco office still handled San Mateo County that year, but those
  files now carry San Jose's district code. San Francisco county plus San Mateo gives 531 against 536 (-0.9%), and
  San Jose is the mirror image (+26.5%). The handover date, about late January 2020, is inferred; ABC does not
  state it.
- **Other years, -4% to -10%:** the same issued-against-approved difference as statewide. ABC publishes no
  per-office "issued" figure to compare with.
- Withdrawal counts per office-year are 19 to 51; a few files either way is a large percentage.

**Does (b) check out?** Issued licences: yes, within 5% every year. Withdrawals: within 5% in five years of
seven, one year unexplained. Priority entries: within 2% every year. I have not started the 2018-to-2003
backfill; that is a judgement call given the one unexplained year.

## 3. (a) The histories

One row per file: licence types, original or transfer, premises address, county, district, each event with its
date, and the basis of the filing date. Statewide: `$LOCAL_DATA_DIR/abc-histories.csv.gz` (no names). San
Francisco: [`abc-sf-histories.csv`](abc-sf-histories.csv).

| Outcome (files) | Statewide | San Francisco county |
|---|---|---|
| Files in the archive | 128,966 | 5,306 |
| No application in the period (licence issued before 2019) | 47,444 | 2,334 |
| **Files with an application** | **81,522** | **2,972** |
| Issued | 62,996 | 2,500 |
| Withdrawn | 13,985 | 285 |
| Denied | 91 | 1 |
| Pending | 4,253 | 183 |
| Temporary permit only | 130 | 2 |
| Unclear | 67 | 1 |

| Class | Statewide | San Francisco county |
|---|---|---|
| Transfer | 37,309 | 1,667 |
| Original | 32,814 | 1,162 |
| Priority-drawing entry | 7,335 | 11 |
| Other (stock, fiduciary, partner changes) | 4,064 | 132 |

Original or transfer comes from the action in Issued Licences or New Applications for 68,107 files and is
inferred from the Transfer-From/To column for 13,415 (withdrawn files show no action). Where both exist the
inference agrees 99.4% of the time for originals and transfers.

## 4. (c) Where applications go from pending, and denials

A file shows only its latest transition, so this counts files by where they stand now.

| Latest transition | Statewide files | San Francisco county |
|---|---|---|
| PEND to ACTIVE | 39,465 | 1,596 |
| PEND to WITHDRAWN | 13,544 | 298 |
| PEND to CANCEL | 876 | 41 |
| NEW to WITHDRAWN | 772 | 1 |
| PEND to DENIED | 91 | 1 |
| PEND to NREN (not renewed) | 83 | 1 |
| PEND to WTHDRN | 31 | 1 |
| PEND to SUREND (surrendered) | 22 | 3 |

A licence issued and later cancelled reads "ACTIVE to CANCEL" and is not in this table; it is counted as issued
from the Issued Licences report.

- **Does a denial appear in Status Changes? Yes:** 91 files statewide. By calendar year: 3, 7, 5, 10, 8, 6, 34,
  and 18 so far in 2026. **San Francisco county has one, in 2020.**
- **Does a denial appear in the Legal Actions reports? No.** All 6,789 files in Legal Actions Filed and all 5,751
  in Finalized (377 weeks each) are accusations against existing licences. None is an application denial.

## 5. (d) Filing dates

| Basis of the filing date | Statewide | San Francisco county |
|---|---|---|
| Estimated from the file number (issued files) | 58,336 | 2,319 |
| First date in Status Changes (never-issued files) | 12,586 | 233 |
| New Applications listing (still pending) | 4,195 | 149 |
| A withdrawn licence type on an issued file | 196 | 5 |
| Unknown (filed before 2019, or one date only) | 6,209 | 266 |

**File numbers run in date order.** Error of a file's date against its neighbours by number:

| Test | N | Median error | p90 | Within 7 days |
|---|---|---|---|---|
| New Applications listings since September 2025 (as asked) | 3,459 | 0.0 days | 0.5 | 99.2% |
| Status Changes first dates, all years | 12,569 | 0.0 days | 0.5 | 99.5% |
| Issued files with an independently known filing date | 208 | 0.0 days | 1.5 | 94.2% |

By application type, on the New Applications listings since September 2025: ORI median 0.0 days, p90 0.5 (N = 1,499); PER 0.0, p90 0.5 (N = 1,159); PRM 0.0, p90 0.5 (N = 174). The error is small for all three, so
older filing dates are estimated from the file number and labelled "estimated".

**San Francisco: Planning's dated ABC referrals matched to file numbers.**

| | |
|---|---|
| Referrals filed since 2019 | 1,582 |
| Matched to an ABC file | 1,081 (68%), on 1,002 files |
| ABC filing date minus Planning referral date | median -3 days (p10 -13, p90 0), N = 921 |
| Within 30 days | 91.3% |

**Hand check of 20 matches:** 16 correct, 3 wrong, 1 cannot tell. All three wrong matches are addresses with
several premises (three hot-dog stands at 599 Skyline Blvd; a shopping centre at 845 Market St). In each, dates
and outcome were the same or the right file was at the same address. Planning's `project_name` field holds the
business name and would have resolved all three; the matcher does not use it yet.

## 6. (e) San Francisco county, 2019 to 2026

Days from filing use the reported filing date where there is one and the file-number estimate otherwise. N is
the number of files with both dates. Where N is under 10 only the count is shown.

| Class | Issued | Withdrawn | Denied | Pending | Filing to issue, median / p90 (N) | Filing to withdrawal, median / p90 (N) |
|---|---|---|---|---|---|---|
| Original | 953 | 108 | 1 | 99 | 97 / 281 days (880) | 162 / 554 days (86) |
| Transfer | 1,417 | 171 | 0 | 77 | 100 / 249 days (1,313) | 158 / 475 days (143) |
| Other | 130 | 0 | 0 | 2 | 58 / 215 days (111) | N = 0 |
| Priority-drawing entry | 0 | 6 | 0 | 5 | N = 0 | N = 4 |

| Type and class | Issued | Withdrawn | Pending | Filing to issue, median / p90 (N) | Filing to withdrawal, median / p90 (N) |
|---|---|---|---|---|---|
| 41 original | 629 | 51 | 60 | 92 / 253 (587) | 197 / 546 (40) |
| 41 transfer | 493 | 53 | 22 | 84 / 181 (455) | 170 / 448 (48) |
| 47 original | 42 | 1 | 2 | 111 / 363 (35) | N = 0 |
| 47 transfer | 431 | 42 | 27 | 116 / 301 (396) | 159 / 603 (31) |
| 47 priority entry | 0 | 6 | 5 | N = 0 | N = 4 |
| 48 transfer | 123 | 19 | 6 | 103 / 298 (113) | 80 / 206 (14) |
| 21 transfer | 237 | 33 | 14 | 97 / 239 (220) | 114 / 657 (27) |
| 20 original | 37 | 4 | 2 | 86 / 153 (31) | N = 4 |
| 20 transfer | 49 | 7 | 3 | 113 / 277 (48) | N = 6 |
| 42 original | 21 | 6 | 3 | 160 / 428 (20) | N = 5 |

Read these with three cautions:

- **Withdrawn is not refused.** The reports give no reason for a withdrawal.
- **Issue times lean on estimated filing dates** (2,319 of the 2,706 San Francisco filing dates). Withdrawal times
  use reported dates.
- **Files filed before 2019 have no filing date** and are left out of the day counts (266 files).

Of San Francisco applications with a known result, 285 were withdrawn and 1 denied against 2,500 issued: about 1
in 10 did not end in a licence.

## 7. (f) San Francisco applications withdrawn since November 2024

[`abc-sf-withdrawn-since-2024-11.csv`](abc-sf-withdrawn-since-2024-11.csv): **85 applications**, withdrawn
2024-12-03 to 2026-11-09. 61 transfers, 23 originals, 1 priority-drawing entry. 80 have a filing date.

Columns: business name, name withheld (yes or no), premises address, licence type, original or transfer (and whether that is inferred),
priority-drawing entry, filing date and its basis, withdrawal date, file number.

**Names.** Company and DBA names only. Where the licensee is an individual, no name is published, DBA
included (a DBA can carry a person's name). Those rows keep the premises address, licence type, original or
transfer and withdrawal date, with the name left blank and `name_withheld` set to yes: 9 of the 85 rows. No
mailing addresses and no care-of lines.

The earlier draft of this file listed 153 rows. That was wrong: it counted filing dates as withdrawals.

## 8. (g) Coverage, San Francisco ABC applications

| Class | Total | Filing date | of which reported | of which estimated | Decision date | Approved | Withdrawn | Denied | Pending |
|---|---|---|---|---|---|---|---|---|---|
| All | 2,972 | 2,706 | 387 | 2,319 | 2,786 | 2,500 | 285 | 1 | 183 |
| Original | 1,162 | 1,050 | 154 | 896 | 1,062 | 953 | 108 | 1 | 99 |
| Transfer | 1,667 | 1,534 | 222 | 1,312 | 1,588 | 1,417 | 171 | 0 | 77 |
| Other | 132 | 113 | 2 | 111 | 130 | 130 | 0 | 0 | 2 |
| Priority-drawing entry | 11 | 9 | 9 | 0 | 6 | 0 | 6 | 0 | 5 |

In Part 1 the ABC pathway had no failures and no filing dates. It now has 286 failures (285 withdrawn, 1 denied),
233 of them with both dates reported, not estimated.

## 9. What this does and does not give the report

- **It gives the alcohol row an outcome history:** counts of issued, withdrawn and denied by licence type, and
  days to each, for San Francisco since 2019.
- **It gives no reasons.** A withdrawal carries no cause, protests are not in these reports, and denials are
  almost absent (one in San Francisco in eight years).
- **It is not wired into the report.** The alcohol row still prints "No outcome history for this pathway yet."

## 10. Limits

- The filing date of an issued application is an estimate from its file number.
- Only the latest transition of a record survives. A withdrawal later reversed is not seen.
- The district code on a file is the office that holds the premises today, not the office that did the work.
- Withdrawals in FY2021-22 are 12.8% under ABC's figure, unexplained.
- Person-to-person transfer investigations are 7% to 16% under ABC's, unexplained.
- The Planning referral matcher mismatches addresses with several premises (3 of 20 in the hand check).
- Company DBAs that are themselves a person's name (a chef's name on a restaurant, for example) are published,
  because the licensee is a company.

## 11. Files

- `abc-histories.json`: every number above, the checks, and the stated limits
- `abc-sf-histories.csv`: San Francisco, one row per file
- `abc-sf-withdrawn-since-2024-11.csv`
- `abc-referral-file-match-sample.csv`: the 20 hand-checked matches
- `abc-workload-summaries.csv`: ABC's published figures as parsed
- `$LOCAL_DATA_DIR/abc-histories.csv.gz`: statewide, one row per file, no names
