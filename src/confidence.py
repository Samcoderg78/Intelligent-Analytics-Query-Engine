"""
Confidence scoring.

This is a heuristic, not a calibrated probability - there's no ground
truth to train against here, so the score is built from things that
plausibly correlate with whether the answer is trustworthy:

  - did we actually understand the query (any unresolved terms?)
  - did we get there via the LLM or the weaker rule-based fallback
  - does the data actually support the question being asked (e.g. a
    year-over-year question when only one year of data exists should
    not come back confident just because the query executed without
    error)
  - is the result empty

Feedback from feedback_log.csv, if present, nudges the score up or down
for queries that look similar to ones a human has already graded.
"""


def score(intent, result, kind, feedback=None):
    value = 1.0

    if intent.get("unresolved_terms"):
        value -= 0.4

    if not intent.get("used_llm"):
        value -= 0.1

    if kind == "yoy" and isinstance(result, dict) and "note" in result:
        value -= 0.5

    if result is None:
        value -= 0.3
    elif isinstance(result, list) and len(result) == 0:
        value -= 0.3

    if feedback is not None:
        value += feedback

    return max(0.0, min(1.0, round(value, 2)))
