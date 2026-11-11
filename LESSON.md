# Syllabuddy: what can we trust from a syllabus extractor?

This is a focused consultation for the Syllabuddy project group. Other
students may observe, but the decisions are about this group's app. The goal
is to leave with a clear distinction between an API request completing, its
response matching a schema, and its facts matching the PDF.

## Evidence we have now

- The ten-PDF feasibility batch had six `success` records and four HTTP 503
  `api_error` records. The 503 messages reported temporary high demand.
- DATA 440 succeeded in two earlier runs, then returned 503 in the batch.
  One other 503 took about 91 seconds. Availability and waiting time can
  change from run to run, even for the same document.
- A `success` record means the request returned text that passed the required
  Pydantic schema. We have not yet checked every extracted fact against its
  source PDF. The batch is small and includes a course-schedule PDF, so its
  six-of-ten outcome is not a general reliability estimate.

## What you should do

1. **Inspect the actual runs.** Use `load_logs()` and print the labels before
   selecting entries. As the log stands now, `logs[2]` is a successful CSCI
   241 extraction and `logs[5]` is a 503 for the DATA 305 syllabus. Open both
   with `print_log()`. Ask what the log proves and what it cannot prove.
2. **Check a source PDF.** Compare a successful record's grade weights and
   dated items against its PDF, using `source_page` to find the evidence.
   Confirm whether dates are classified as assignment or administrative.
   The CSCI 141 result lists 38 objectives; inspect that PDF before deciding
   whether this is appropriate detail or over-extraction.
3. **Show a controlled retry.** Run the mocked retry-then-success test in
   `tests/test_retry_example.py`. It produces a 503 followed by a valid
   response without making an API call or waiting. Contrast its two attempts
   with the feasibility test's one-call outcome.
4. **Decide what the app should say.** What should a user see after a 503?
   Which extracted due dates and grading weights must a person confirm from
   the syllabus before they are trusted? Decide how to mark unverified fields
   and how to correct them.

To show the simulated retry messages, run
`uv run python -m unittest discover -s tests -p test_retry_example.py -v`
from the project root. In a Jupyter cell, prefix the command with `!`. The
test replaces the network call and the sleep, so the displayed four-second
wait is instructional, not real time.

## Reliability questions for the group

- **Availability:** How often does one attempt succeed, and how long does it
  take? A later retry study should report both attempts and final outcomes.
- **Schema validity:** Did the response contain every required field in the
  expected shape? Passing this check says nothing about factual correctness.
- **Accuracy:** For each field, was it present in the PDF, on the cited page,
  and classified correctly? Check both missing facts and invented facts.
- **Variation:** Does the same PDF give different facts on repeated runs?
  The current log shows availability variation but does not establish factual
  variation.
- **Document type:** A course schedule may legitimately have no grade weights
  or objectives. Evaluation should note what each source actually contains.

Retries may help a user finish a request, but they add calls and waiting time.
They do not validate the extracted facts. The starter example retries only
selected temporary HTTP statuses and stops after three attempts; it is not a
complete production policy. The group still needs to design the rest of its
pipeline and decide how to measure factual accuracy.

## Findings to add later

- Record a manual check of representative successful PDFs, including the
  claimed source pages, omitted items, and any invented items.
- Compare first-attempt completion with completion after retries, keeping the
  number of calls and elapsed time visible.
- Record decisions about user-facing verification and correction of dates and
  grade weights.
