"""
feedback_log.csv was listed as optional in the brief and wasn't included
in the dataset provided, so there's nothing to load in this run. The
mechanism is still built out because it's a normal part of a system like
this: over time, someone marks a handful of answers right or wrong, and
that should count for something the next time the same or a similar
question comes in, rather than the system reasoning it out from scratch
every time with equal confidence.

Expected columns: query, correct (yes/no), notes
A close match (case-insensitive, ignoring punctuation) on a past query
nudges the confidence score for the new one up or down slightly. This is
intentionally a small nudge, not a lookup table of answers - the point is
to bias confidence, not to hardcode results.
"""

import csv
import os
import re


def _normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def load(dataset_dir):
    path = os.path.join(dataset_dir, "feedback_log.csv")
    if not os.path.exists(path):
        return {}

    entries = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = _normalize(row.get("query", ""))
            correct = str(row.get("correct", "")).strip().lower() in ("yes", "true", "1")
            if q:
                entries[q] = correct
    return entries


def adjustment(query, feedback_entries):
    if not feedback_entries:
        return None
    q = _normalize(query)
    if q in feedback_entries:
        return 0.1 if feedback_entries[q] else -0.3
    return None
