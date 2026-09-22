"""
Runs every query in dataset/nl_queries.json through the engine and writes
the results to output/output.json, printing each one to the console as it
goes so you can see what happened without opening the file.

Usage:
    python main.py                       runs every query in the dataset
    python main.py "your own question"   runs a single ad-hoc question
"""

import json
import os
import sys

from src.data_loader import build_database, load_data_dictionary, load_nl_queries
from src.engine import QueryEngine
from src.schema import Schema

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def main():
    conn = build_database(DATASET_DIR)
    data_dictionary = load_data_dictionary(DATASET_DIR)
    schema = Schema(data_dictionary, conn)
    engine = QueryEngine(conn, schema, DATASET_DIR)

    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        queries = [q["query"] for q in load_nl_queries(DATASET_DIR)]

    results = []
    for query in queries:
        result = engine.answer(query)
        results.append(result)
        print(json.dumps(result, indent=2, default=str))
        print("-" * 60)

    if len(sys.argv) == 1:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, "output.json")
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nWrote {len(results)} results to {out_path}")


if __name__ == "__main__":
    main()
