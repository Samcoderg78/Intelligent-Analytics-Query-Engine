# Intelligent Analytics Query Engine

Converts natural language questions about a sales dataset into SQL, executes them, and returns the result with a confidence score and a plain-language explanation.

## Features

- Natural language to SQL translation (aggregations, grouping, filtering, ranking, target comparisons, YoY growth, contribution %)
- Executes generated SQL against an in-memory SQLite database
- GenAI-powered query understanding (Gemini API), with a rule-based fallback when no API key is set
- Confidence score per query
- Human-readable explanation per query
- Optional feedback loop via `feedback_log.csv`

## Setup

```bash
git clone <repo-url>
cd analytics_query_engine
pip install -r requirements.txt
```

GenAI usage is optional. To enable it, get a free key from [Google AI Studio](https://aistudio.google.com) and set it as an environment variable:

```bash
# macOS / Linux
export GEMINI_API_KEY="AIza..."

# Windows PowerShell
$env:GEMINI_API_KEY = "AIza..."
```

Without a key set, the system runs fully offline using a rule-based parser.

## Usage

Run all queries from `dataset/nl_queries.json`:

```bash
python main.py
```

Results are printed to the console and written to `output/output.json`.

Run a single ad-hoc query:

```bash
python main.py "Top 3 customers in EMEA"
```

## Output format

```json
{
  "query": "Total sales in India for March",
  "generated_logic": "SELECT SUM(revenue) AS revenue FROM sales_v WHERE country = 'India' AND month = '2024-03';",
  "result": 108.0,
  "confidence_score": 1.0,
  "explanation": "The question asked for the overall sales revenue generated in India during March 2024. This was calculated by summing the revenue field after filtering by country and month."
}
```

## Requirements

- Python 3.9+
- `requests`

## License

For evaluation purposes as part of an assignment submission.
