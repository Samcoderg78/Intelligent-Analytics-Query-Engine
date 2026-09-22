# Intelligent Analytics Query Engine

Converts natural language questions about the sales dataset into SQL, runs
that SQL, and returns the result along with a confidence score and a plain
language explanation of what was understood and how the answer was
produced.

## Running it

```
pip install -r requirements.txt
python main.py
```

This reads every query in `dataset/nl_queries.json`, prints each result to
the console, and writes the full list to `output/output.json`.

To try a single question of your own instead of the file:

```
python main.py "Top 3 customers in EMEA"
```

GenAI is optional. If a `GEMINI_API_KEY` environment variable is set, the
engine calls Gemini (via Google AI Studio's free tier) to parse the query
and to write the explanation. If it isn't set, the engine falls back to a
rule-based parser and a templated explanation, and everything still runs
end to end. The `sample_output.json` included in this submission was
generated in fallback mode, since no key was configured in the
environment I built this in - the shape of the output is identical
either way, only the parsing method differs (see `used_llm` inside the
intent, and the wording of the explanation).

To use the GenAI path: get a free key at https://aistudio.google.com
("Get API key" - no billing setup required), then
`export GEMINI_API_KEY="AIza..."` before running `main.py`.

## Approach

I didn't want to write a special case per question in `nl_queries.json`
that would fall apart on anything not in that exact list. Instead I split
the problem into two things that don't need to know about each other:

1. **Understanding the question.** A query gets turned into a small
   structured object (`intent_parser.py` calls it "intent") - which metric,
   which dimensions to group by, which filters, whether it's asking for a
   top-N, a percentage of total, a target comparison, or year-over-year
   growth. This is the step that actually uses GenAI: the query text plus
   a description of the schema goes to Gemini, and it returns that
   structured object as JSON (using Gemini's structured JSON output mode,
   so the response is guaranteed to be valid JSON rather than something
   that has to be coaxed out of free-form text). If the API isn't
   available, a rule-based parser (regex plus lookups against the data
   dictionary's synonym table and the dataset's own distinct values)
   produces the same shape of object using simpler pattern matching.

2. **Turning that into SQL and running it.** `sql_builder.py` never looks
   at the original English at all - it only sees the intent object, and
   assembles a real SQL statement from it (plain aggregation, GROUP BY,
   ORDER BY / LIMIT, a window function for "top N within each group", a
   join against `targets.csv` for target comparisons, a subquery for
   contribution percentages). That SQL runs against an in-memory SQLite
   database built from the two CSVs, using `executor.py`.

Keeping those two steps separate is what makes the system generalise:
"top 2 cities by profit" and "bottom 3 products by revenue" go through the
exact same code path in `sql_builder.py`, they just produce a different
intent object on the way in.

Year-over-year growth is the one place that needs a small second pass in
Python after the SQL runs, because a percentage change across two rows
isn't naturally a single SQL aggregate - the SQL gets the yearly totals,
and `executor.py` computes the growth from those.

## Architecture

```
main.py                 entry point - loads data, runs each query, writes output.json

src/
  data_loader.py         reads the CSV/JSON files and loads them into SQLite
  schema.py              data dictionary + distinct column values, used by the parser
  llm_client.py          thin wrapper around the Gemini API, returns None on any failure
  intent_parser.py       query text -> structured intent (LLM first, rule-based fallback)
  sql_builder.py         structured intent -> SQL string
  executor.py            runs the SQL, shapes the result, computes YoY growth
  confidence.py          heuristic confidence score for a result
  explain.py             plain-language explanation (LLM, or a template)
  feedback.py            reads feedback_log.csv if present, nudges confidence
  engine.py              wires the above together for a single query
```

### A note on the input files

`sales_data.csv`, `targets.csv`, `data_dictionary.json` and `nl_queries.json`
all had the same problem: every line was wrapped in an extra pair of
quotes with internal quotes doubled, on top of a UTF-8 BOM and Windows line
endings - the kind of thing that happens when a file gets re-exported by a
tool that doesn't realise the content is already quoted. `data_loader.py`
undoes that before parsing anything else, so the rest of the code just
deals with normal CSV and JSON.

`revenue` isn't a column in `sales_data.csv` - the data dictionary defines
it as `quantity * unit_price * (1 - discount)`. It's added as a computed
column in a SQLite view (`sales_v`) rather than stored, so it can never
drift out of sync with the raw columns, and it's not "hardcoded", it's the
formula from the dictionary literally executed as SQL.

## Confidence score

There's no ground truth to calibrate against, so this is a heuristic, not
a trained probability. It starts at 1.0 and is reduced when:

- parsing didn't recognise something in the query (unresolved terms)
- the rule-based fallback parser was used instead of the LLM
- the result is empty or missing
- the question needs data the dataset doesn't have enough of - the
  YoY query is a good example: it runs without error, but there's only one
  year of data in this dataset, so the confidence is deliberately low even
  though the SQL executed fine

`feedback_log.csv` (see below) can nudge this further for queries that
look like ones a person has already graded.

## Feedback loop

The brief mentions `feedback_log.csv` as optional, and it wasn't included
in the dataset I was given, so there's nothing for it to load in this run.
`feedback.py` still implements it, though, because it's a normal part of
a system like this: expected columns are `query, correct, notes`, and a
close text match against a past query nudges the new confidence score up
or down slightly. It's a nudge, not a lookup table of answers - it doesn't
change the generated SQL or the result, only how confident the system says
it is.

## Tradeoffs and things I'd do differently with more time

- **The rule-based fallback is pattern matching, not real understanding.**
  It works for the phrasing style used in `nl_queries.json` and the
  variations I tried, but it will miss anything phrased very differently.
  The LLM path handles that far better, which is exactly why it's the
  primary path and the fallback exists mainly so the system still runs
  without a key.
- **Ambiguous "top N" phrasing.** "Top product in each region" and
  "revenue of top 3 customers per region" look similar on the surface but
  want different shapes of answer back (the top rows themselves, versus an
  aggregate over them). I handled this with a `rollup` flag rather than
  trying to infer it purely from sentence structure - it works for these
  cases but a genuinely ambiguous question could still go either way.
- **Only one year of data.** Year-over-year growth can't really be
  answered from this dataset. I chose to surface that honestly (low
  confidence, a clear note in the result) rather than pretend the number
  means something.
- **Confidence is heuristic.** With real usage data and actual right/wrong
  labels in `feedback_log.csv`, this could become a proper calibrated
  score instead of a rule-of-thumb.
- **Single-table dataset.** With more time and a bigger schema, I'd want
  the LLM prompt in `intent_parser.py` to include a short sample of
  distinct values per column (it currently only gets the dictionary), so
  it can resolve ambiguous entity names (a city that shares a name with a
  country, for example) with more context.
- **No caching.** Every call re-parses and re-queries from scratch. For a
  larger query volume, caching the SQL for a normalised query string would
  cut both cost and latency.

## Sample outputs

See `output/output.json` for the full output on all eight queries in
`dataset/nl_queries.json`, and `sample_output.json` in this folder for a
copy of the same file kept alongside the README for convenience.
