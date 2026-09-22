# Intelligent Analytics Query Engine

Converts natural-language questions about the sales dataset into SQL, runs the query, and returns:

- the result
- a confidence score
- a plain-language explanation of what was understood and how the answer was produced

## Setup

```bash
pip install -r requirements.txt
```

## Run all default queries

```bash
python main.py
```

This reads each query from `dataset/nl_queries.json` and writes all results to `output/output.json`.

## Run one custom question

```bash
python main.py "Top 3 customers in EMEA"
```

## Optional Gemini integration

If `GEMINI_API_KEY` is set, the app uses Gemini for parsing and explanation generation. If it is not set, the app automatically falls back to the built-in rule-based parser.

```bash
export GEMINI_API_KEY="AIza..."
python main.py
```
