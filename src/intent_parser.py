"""
Converts a natural language query into a structured "intent" dictionary.
Everything downstream (sql_builder.py) works off this dictionary, not off
the raw text, so it doesn't matter whether the dictionary came from the
LLM or from the fallback parser below - the shape is always the same:

{
  "metric": "revenue" | "profit" | "orders" | "avg_order_value",
  "group_by": [<dimension column name>, ...],
  "filters": {"country": "India", "month": "2024-03", ...},
  "top_n": int or None,
  "order": "desc" | "asc",
  "partition_by": <dimension column> or None,   # for "top N per group"
  "contribution_pct": bool,
  "compare_target": bool,
  "yoy": bool,
  "used_llm": bool,          # for confidence scoring / explanations
  "unresolved_terms": [...]  # words we couldn't map to anything, if any
}

The LLM path is tried first (when a key is configured). It's given the
data dictionary as context so it maps business language the same way a
rule-based system would, just with far better generalisation to phrasing
nobody anticipated. The rule-based path is the fallback - it's what runs
this project offline, and it's also what keeps the system usable if the
API is down or rate limited, which matters more for a "confidence score"
type of product than a single clever answer would.
"""

import re

from . import llm_client

DIMENSION_COLUMNS = [
    "region", "country", "city", "customer_segment",
    "product_category", "product_subcategory", "product_name", "customer_id",
]

INTENT_SCHEMA_PROMPT = """You convert an analytics question into a JSON object, nothing else.

Available metrics: revenue, profit, orders, avg_order_value
Available dimensions to group or filter by: region, country, city, customer_segment,
product_category, product_subcategory, product_name, customer_id, month, year

Return exactly this JSON shape, no extra keys, no commentary:
{
  "metric": one of the metrics above,
  "group_by": [dimension names, empty list if none],
  "filters": {dimension name: value, ...},
  "top_n": integer or null,
  "order": "desc" or "asc",
  "partition_by": dimension name or null (only when the question asks for a
      top-N *within each* group, e.g. "top product in each region"),
  "contribution_pct": true/false (true when asking for a share/percentage of total),
  "compare_target": true/false (true when asking about hitting/missing a target),
  "target_status": "missed", "met", or null (only set when compare_target is true),
  "yoy": true/false (true for year over year growth questions),
  "rollup": true/false (true only for questions like "revenue of top 3 customers per
      region", where the answer is an aggregated number per group, not the list of
      top rows themselves; false for questions like "top product in each region",
      which want the top row(s) returned as-is)
}

Month filters should be written as "YYYY-MM". If a year is not mentioned, use 2024,
since that is the only year present in this dataset.
"""


def parse(query, schema):
    intent = None
    if llm_client.is_available():
        intent = _parse_with_llm(query, schema)
    if intent is None:
        intent = _parse_with_rules(query, schema)
    return intent


def _parse_with_llm(query, schema):
    raw = llm_client.ask_json(INTENT_SCHEMA_PROMPT, query)
    if not isinstance(raw, dict) or "metric" not in raw:
        return None
    intent = _default_intent()
    intent.update({k: v for k, v in raw.items() if k in intent})
    intent["used_llm"] = True
    return intent


def _default_intent():
    return {
        "metric": "revenue",
        "group_by": [],
        "filters": {},
        "top_n": None,
        "order": "desc",
        "partition_by": None,
        "contribution_pct": False,
        "compare_target": False,
        "target_status": None,
        "yoy": False,
        "rollup": False,
        "used_llm": False,
        "unresolved_terms": [],
    }


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

def _parse_with_rules(query, schema):
    text = query.lower()
    intent = _default_intent()

    metric = _find_metric(text, schema)
    if metric:
        intent["metric"] = metric
    elif "profit" in text:
        intent["metric"] = "profit"

    if re.search(r"\baverage\b|\bavg\b", text) and "average_already_set" not in text:
        if intent["metric"] != "avg_order_value" and ("order value" in text or "aov" in text):
            intent["metric"] = "avg_order_value"

    if "contribution" in text or "% " in text or "percentage" in text or text.strip().endswith("%"):
        intent["contribution_pct"] = True

    if "target" in text or "missed" in text or "met its" in text:
        intent["compare_target"] = True
        if "missed" in text or "below" in text or "under" in text:
            intent["target_status"] = "missed"
        elif "met" in text or "achieved" in text or "exceeded" in text or "hit" in text:
            intent["target_status"] = "met"

    if "yoy" in text or "year over year" in text or "year-over-year" in text:
        intent["yoy"] = True

    if re.match(r"^(revenue|sales|profit|income|earnings)\s+of\s+top", text):
        intent["rollup"] = True

    top_match = re.search(r"top\s+(\d+)", text)
    bottom_match = re.search(r"bottom\s+(\d+)", text)
    if top_match:
        intent["top_n"] = int(top_match.group(1))
    elif bottom_match:
        intent["top_n"] = int(bottom_match.group(1))
    elif re.search(r"\btop\b", text):
        intent["top_n"] = 1

    if re.search(r"\bbottom\b|\blowest\b|\bleast\b", text):
        intent["order"] = "asc"

    filters, month_terms = _find_filters(text, schema)
    intent["filters"].update(filters)

    each_match = re.search(r"in each (\w[\w\s]*)|per (\w[\w\s]*)", text)
    if each_match:
        phrase = (each_match.group(1) or each_match.group(2)).strip()
        col = _match_dimension_phrase(phrase, schema)
        if col:
            intent["partition_by"] = col
            if intent["top_n"] is None:
                intent["top_n"] = 1

    group_dims = _find_group_by(text, schema, exclude=intent["partition_by"])
    if group_dims:
        intent["group_by"] = group_dims
    elif intent["partition_by"] and "customer" in text and "customer_id" not in intent["group_by"]:
        intent["group_by"] = ["customer_id"]
    elif intent["partition_by"] and not group_dims:
        # "top product in each region" -> rank product_name within region
        for phrase, col in [("product", "product_name"), ("city", "city"),
                             ("category", "product_category"), ("customer", "customer_id")]:
            if phrase in text:
                intent["group_by"] = [col]
                break

    if not intent["used_llm"] and not metric and not intent["group_by"] and not intent["filters"]:
        intent["unresolved_terms"].append(query)

    return intent


def _find_metric(text, schema):
    for word, mapped in schema.synonyms.items():
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            resolved = schema.resolve_metric(word)
            if resolved:
                return resolved
    for name in schema.metrics:
        if re.search(r"\b" + re.escape(name.replace("_", " ")) + r"\b", text):
            return name
    if "orders" in text or "number of orders" in text:
        return "orders"
    return None


def _find_filters(text, schema):
    from . import schema as schema_module
    filters = {}
    month_terms = []

    for dim, values in schema.dimension_values.items():
        for value in values:
            if value.lower() in text and re.search(r"\b" + re.escape(value.lower()) + r"\b", text):
                filters[dim] = value

    for name, num in schema_module.MONTH_NAMES.items():
        if re.search(r"\b" + name + r"\b", text):
            year_match = re.search(r"\b(20\d\d)\b", text)
            year = year_match.group(1) if year_match else (schema.years[-1] if schema.years else "2024")
            filters["month"] = f"{year}-{num}"
            month_terms.append(name)
            break

    return filters, month_terms


def _match_dimension_phrase(phrase, schema):
    phrase = phrase.strip().rstrip("s")
    for col, aliases in schema.dimension_aliases.items():
        for alias in aliases:
            if alias.rstrip("s") in phrase or phrase in alias:
                return col
    for col in DIMENSION_COLUMNS:
        if col.replace("_", " ").rstrip("s") in phrase:
            return col
    return None


def _find_group_by(text, schema, exclude=None):
    found = []
    patterns = {
        "region": r"\bby region\b|\bregions\b",
        "country": r"\bby country\b|\bcountries\b",
        "city": r"\bby city\b|\bcities\b",
        "customer_segment": r"\bby segment\b|\bby customer segment\b",
        "product_category": r"\bby category\b|\bcategories\b",
        "product_subcategory": r"\bby subcategory\b",
        "customer_id": r"\bby customer\b|\bcustomers\b",
        "product_name": r"\bby product\b|\bproducts\b",
    }
    for col, pattern in patterns.items():
        if col == exclude:
            continue
        if re.search(pattern, text):
            found.append(col)
    return found
