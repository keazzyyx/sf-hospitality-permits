## Coverage

This is the detail behind the coverage note on the search page. The numbers in the table above it come from the
data the page loads, so they always match what you can search.

### What is included

- **Type of decision.** San Francisco Planning Commission motions on Conditional Use cases. An amendment to an
  earlier approval counts as its own case.
- **Type of premises.** Food, drink and entertainment premises: restaurants and cafes, bars, nighttime
  entertainment, and other food and drink businesses.
- **Outcome.** Approved, approved with conditions, or denied. A denial usually has no conditions.
- **Dates.** Cases decided on or after 1 January 2010, up to the date Planning's records were last copied (in the
  table above).

### How the motions were found and picked

1. **Cases.** Every Conditional Use case in Planning's public records (DataSF) decided since 1 January 2010 that
   was approved, approved with conditions or denied, and that was labelled a food, drink or entertainment premises.
2. **Motions.** For each case, the motion PDF was looked up in Planning's hearing documents, and every numbered
   condition was taken from its conditions section.
3. **Food-or-drink check.** An automated classifier labelled each case. A motion is kept only when the
   classifier says it is about a food, drink or entertainment premises.
4. **Review.** An AI review then read each motion and corrected the classifier where it was wrong: some
   motions it left out were added back (with the business type the review gives), and some it kept were taken
   off. The reviewed list above gives each change and its reason. The motions left out are listed below.
5. **Conditions.** Each condition is shown with its number, title and text, the business type, the zoning
   district, the decision date and a link to the motion.

### What is not included

- Motions that are not about a food, drink or entertainment premises, after the review (listed below).
- Cases with no motion in Planning's hearing documents (listed in the table above).
- Motions with no conditions section.
- Cases decided before 1 January 2010, and cases decided after Planning's records were last copied.
- Entertainment Commission permits and their conditions.
- Board of Appeals decisions.
- State alcohol licence (ABC) conditions.
- Building permits.
- Approvals made without a Planning Commission motion, such as administrative approvals.

### Known gaps

- **The picking can be wrong.** The classifier's mistakes that the review found are corrected (see the
  reviewed list above). A motion the review did not catch can still be on the wrong side. Grocery stores and
  supermarkets (a General or Specialty Grocery use) are left out, even with a deli or cafe inside; a store
  Planning approved as a Liquor Store use is shown as other food and drink.
- **Some text could not be read.** Older motions are scanned. Where the first reading of a condition was
  garbled, it was read again from the PDF's text layer or by OCR. A few conditions still could not be read
  cleanly; they are marked and link to the motion page instead. Single misread words can still appear.
- **Some page links are approximate.** Some conditions link to a page near the condition ("near page") rather
  than the page where it starts.
- **The motion PDFs are copies kept in the site's file storage.** Page links open a copy of the adopted
  motion, and the browser opens it at the page where the condition starts (or near it). The copies are made
  smaller: same pages in the same order, pictures at a lower resolution, and plan drawings outside the
  conditions turned into pictures of the page. Planning's own copy is linked next to each condition; Planning's
  link downloads the PDF instead of opening it at the page.
- **Not up to the minute.** Nothing decided after Planning's records were last copied is here.
- **Not legal advice.** The conditions are copied from public records. Always check the motion itself.
