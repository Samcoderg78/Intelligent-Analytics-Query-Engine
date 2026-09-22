"""
Builds a SQL statement from the structured intent produced by
intent_parser.py. This is deliberately templated rather than one-off per
query - the same handful of building blocks (metric expression, WHERE
clause, GROUP BY, window function ranking) gets combined differently
depending on which flags are set in the intent, so a query the parser has
never seen before still produces valid SQL as long as it maps to a
combination of these flags.
"""

METRIC_EXPR = {
    "revenue": "SUM(revenue)",
    "profit": "SUM(profit)",
    "orders": "COUNT(DISTINCT order_id)",
    "avg_order_value": "SUM(revenue) * 1.0 / COUNT(DISTINCT order_id)",
}

FILTER_COLUMNS = {
    "region", "country", "city", "customer_segment",
    "product_category", "product_subcategory", "product_name",
    "customer_id", "month", "year",
}


def _metric_expr(metric):
    return METRIC_EXPR.get(metric, METRIC_EXPR["revenue"])


def _where_clause(filters):
    conditions = []
    for col, value in filters.items():
        if col not in FILTER_COLUMNS:
            continue
        safe_value = str(value).replace("'", "''")
        conditions.append(f"{col} = '{safe_value}'")
    if not conditions:
        return ""
    return "WHERE " + " AND ".join(conditions)


def build(intent):
    """Returns (sql, kind) where kind tells executor.py how to interpret
    the result set (single value, table, or "needs a second pass in
    Python", as with YoY growth)."""

    if intent["yoy"]:
        return _build_yoy(intent), "yoy"

    if intent["compare_target"]:
        return _build_target_comparison(intent), "table"

    if intent["partition_by"]:
        return _build_partitioned_rank(intent), "table"

    if intent["contribution_pct"]:
        return _build_contribution(intent), "table"

    return _build_plain_aggregation(intent), ("scalar" if not intent["group_by"] else "table")


def _build_plain_aggregation(intent):
    metric_expr = _metric_expr(intent["metric"])
    where = _where_clause(intent["filters"])
    group_by = intent["group_by"]

    if not group_by:
        sql = f"SELECT {metric_expr} AS {intent['metric']} FROM sales_v"
        if where:
            sql += f" {where}"
        return sql + ";"

    cols = ", ".join(group_by)
    sql = f"SELECT {cols}, {metric_expr} AS {intent['metric']} FROM sales_v"
    if where:
        sql += f" {where}"
    sql += f" GROUP BY {cols}"
    order = intent.get("order", "desc").upper()
    sql += f" ORDER BY {intent['metric']} {order}"
    if intent["top_n"]:
        sql += f" LIMIT {int(intent['top_n'])}"
    return sql + ";"


def _build_contribution(intent):
    metric_expr = _metric_expr(intent["metric"])
    where = _where_clause(intent["filters"])
    group_by = intent["group_by"] or ["product_category"]
    cols = ", ".join(group_by)

    total_where = where
    sql = (
        f"SELECT {cols}, {metric_expr} AS {intent['metric']}, "
        f"ROUND({metric_expr} * 100.0 / "
        f"(SELECT {metric_expr} FROM sales_v {total_where}), 2) AS contribution_pct "
        f"FROM sales_v"
    )
    if where:
        sql += f" {where}"
    sql += f" GROUP BY {cols} ORDER BY contribution_pct DESC;"
    return sql


def _build_target_comparison(intent):
    metric_expr = _metric_expr(intent["metric"]).replace("sales_v", "s")
    metric_expr_s = metric_expr.replace("SUM(revenue)", "SUM(s.revenue)").replace(
        "COUNT(DISTINCT order_id)", "COUNT(DISTINCT s.order_id)"
    )
    where_parts = []
    for col, value in intent["filters"].items():
        if col not in FILTER_COLUMNS:
            continue
        safe_value = str(value).replace("'", "''")
        prefix = "s." if col != "month" else "s."
        where_parts.append(f"{prefix}{col} = '{safe_value}'")
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    having = ""
    if intent["target_status"] == "missed":
        having = "HAVING actual_revenue < t.target_revenue"
    elif intent["target_status"] == "met":
        having = "HAVING actual_revenue >= t.target_revenue"

    sql = (
        "SELECT s.region, s.month, SUM(s.revenue) AS actual_revenue, t.target_revenue "
        "FROM sales_v s JOIN targets t ON s.region = t.region AND s.month = t.month "
        f"{where_sql} "
        "GROUP BY s.region, s.month, t.target_revenue "
        f"{having};"
    )
    return sql


def _build_partitioned_rank(intent):
    metric_expr = _metric_expr(intent["metric"])
    where = _where_clause(intent["filters"])
    partition = intent["partition_by"]
    rank_dims = intent["group_by"] or ["product_name"]
    rank_cols = ", ".join(rank_dims)
    top_n = intent["top_n"] or 1

    inner = (
        f"SELECT {partition}, {rank_cols}, {metric_expr} AS {intent['metric']}, "
        f"RANK() OVER (PARTITION BY {partition} ORDER BY {metric_expr} DESC) AS rnk "
        f"FROM sales_v"
    )
    if where:
        inner += f" {where}"
    inner += f" GROUP BY {partition}, {rank_cols}"

    if intent["rollup"]:
        sql = (
            f"WITH ranked AS ({inner}) "
            f"SELECT {partition}, SUM({intent['metric']}) AS {intent['metric']} "
            f"FROM ranked WHERE rnk <= {top_n} GROUP BY {partition} ORDER BY {partition};"
        )
    else:
        sql = (
            f"WITH ranked AS ({inner}) "
            f"SELECT {partition}, {rank_cols}, {intent['metric']} "
            f"FROM ranked WHERE rnk <= {top_n} ORDER BY {partition}, rnk;"
        )
    return sql


def _build_yoy(intent):
    metric_expr = _metric_expr(intent["metric"])
    where = _where_clause({k: v for k, v in intent["filters"].items() if k != "month"})
    sql = f"SELECT year, {metric_expr} AS {intent['metric']} FROM sales_v"
    if where:
        sql += f" {where}"
    sql += " GROUP BY year ORDER BY year;"
    return sql
