from . import llm_client

EXPLAIN_SYSTEM_PROMPT = """You write a two sentence explanation of how an analytics
question was answered. First sentence: what the question was asking for, in plain
words. Second sentence: what calculation produced the result. Be specific about
which fields/filters were used. No preamble, no markdown, just the two sentences."""


def build(query, intent, sql, result):
    if llm_client.is_available():
        prompt = (
            f"Question: {query}\n"
            f"Parsed as: {intent}\n"
            f"SQL executed: {sql}\n"
            f"Result: {result}"
        )
        text = llm_client.ask_text(EXPLAIN_SYSTEM_PROMPT, prompt)
        if text:
            return text
    return _template_explanation(intent, sql)


def _template_explanation(intent, sql):
    metric = intent["metric"].replace("_", " ")
    parts = [f"Understood as a request for {metric}"]

    if intent["filters"]:
        filter_desc = ", ".join(f"{k}={v}" for k, v in intent["filters"].items())
        parts.append(f"filtered by {filter_desc}")

    if intent["group_by"]:
        parts.append(f"grouped by {', '.join(intent['group_by'])}")

    if intent["partition_by"]:
        parts.append(f"ranked separately within each {intent['partition_by']}")

    if intent["top_n"]:
        direction = "bottom" if intent.get("order") == "asc" else "top"
        parts.append(f"limited to the {direction} {intent['top_n']}")

    if intent["contribution_pct"]:
        parts.append("expressed as a percentage of the overall total")

    if intent["compare_target"]:
        parts.append("compared against the target_revenue in targets.csv")

    if intent["yoy"]:
        parts.append("comparing the latest year in the data against the previous year")

    understood = ", ".join(parts) + "."
    generated = f" This was translated into SQL and executed directly against the dataset: {sql}"
    return understood + generated
