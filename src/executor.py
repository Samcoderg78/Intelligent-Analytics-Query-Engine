"""
Executes the SQL that sql_builder.py produced and turns the raw rows into
the kind of result value that belongs in the final output: a plain number
for a scalar query, a list of dicts for anything grouped, and (for YoY) a
small growth calculation on top of the yearly totals since a percentage
change isn't something SQL alone gives you without a self join.
"""


def run(conn, sql, kind):
    cur = conn.cursor()
    cur.execute(sql)
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    if kind == "scalar":
        if not rows:
            return None
        value = list(rows[0].values())[0]
        return round(value, 2) if isinstance(value, float) else value

    if kind == "yoy":
        return _yoy_growth(rows)

    for row in rows:
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = round(v, 2)
    return rows


def _yoy_growth(rows):
    if len(rows) < 2:
        return {
            "note": "insufficient data for year-over-year growth",
            "yearly_totals": rows,
        }
    rows = sorted(rows, key=lambda r: r["year"])
    latest, previous = rows[-1], rows[-2]
    metric_key = [k for k in latest if k != "year"][0]
    prev_value = previous[metric_key]
    latest_value = latest[metric_key]
    growth_pct = None
    if prev_value:
        growth_pct = round((latest_value - prev_value) / prev_value * 100, 2)
    return {
        "previous_year": previous["year"],
        "previous_value": round(prev_value, 2),
        "latest_year": latest["year"],
        "latest_value": round(latest_value, 2),
        "growth_pct": growth_pct,
    }
