"""
Loads the four input files.

Note: the files as received are not plain CSV / JSON. Every line has been
wrapped in an extra pair of quotes and internal quotes have been doubled
(this is what you get when a spreadsheet tool re-exports a file that was
already quoted once - it quotes it again). There is also a UTF-8 BOM and
Windows line endings on every file.

_unwrap_lines() below undoes that one-time export mistake so the rest of
the code can just work with normal CSV / JSON. If a "clean" file is ever
given to this project directly, _unwrap_lines() is a no-op for it, so it
is safe to always run.
"""

import csv
import io
import json
import os
import sqlite3


def _unwrap_lines(raw_text):
    lines = raw_text.replace("\r\n", "\n").split("\n")
    fixed = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        s = s.replace('""', '"')
        fixed.append(s)
    return "\n".join(fixed)


def _read_and_fix(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    return _unwrap_lines(raw)


def load_csv_rows(path):
    text = _read_and_fix(path)
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def load_json(path):
    text = _read_and_fix(path)
    return json.loads(text)


NUMERIC_SALES_COLS = ["quantity", "unit_price", "discount", "shipping_cost", "profit"]


def build_database(dataset_dir, db_path=":memory:"):
    """
    Loads sales_data.csv and targets.csv into a SQLite database and adds a
    view (sales_v) that exposes the derived fields (revenue, month, year)
    so the query builder can just SELECT from them like any other column.
    """
    sales_rows = load_csv_rows(os.path.join(dataset_dir, "sales_data.csv"))
    target_rows = load_csv_rows(os.path.join(dataset_dir, "targets.csv"))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE sales (
            order_id INTEGER,
            order_date TEXT,
            region TEXT,
            country TEXT,
            city TEXT,
            customer_id TEXT,
            customer_segment TEXT,
            product_category TEXT,
            product_subcategory TEXT,
            product_name TEXT,
            quantity REAL,
            unit_price REAL,
            discount REAL,
            shipping_cost REAL,
            profit REAL
        )
    """)
    for row in sales_rows:
        clean = dict(row)
        for col in NUMERIC_SALES_COLS:
            clean[col] = float(clean[col])
        clean["order_id"] = int(float(clean["order_id"]))
        cur.execute(
            """INSERT INTO sales VALUES
               (:order_id,:order_date,:region,:country,:city,:customer_id,
                :customer_segment,:product_category,:product_subcategory,
                :product_name,:quantity,:unit_price,:discount,
                :shipping_cost,:profit)""",
            clean,
        )

    cur.execute("""
        CREATE TABLE targets (
            region TEXT,
            month TEXT,
            target_revenue REAL
        )
    """)
    for row in target_rows:
        cur.execute(
            "INSERT INTO targets VALUES (:region,:month,:target_revenue)",
            {**row, "target_revenue": float(row["target_revenue"])},
        )

    # revenue is derived, not stored, per the data dictionary formula:
    # revenue = quantity * unit_price * (1 - discount)
    cur.execute("""
        CREATE VIEW sales_v AS
        SELECT *,
               quantity * unit_price * (1 - discount) AS revenue,
               substr(order_date, 1, 7) AS month,
               substr(order_date, 1, 4) AS year
        FROM sales
    """)

    conn.commit()
    return conn


def load_data_dictionary(dataset_dir):
    return load_json(os.path.join(dataset_dir, "data_dictionary.json"))


def load_nl_queries(dataset_dir):
    return load_json(os.path.join(dataset_dir, "nl_queries.json"))
