"""Run every query in sql/analysis.sql and save each result.

Each query is marked with a "-- name: <name>" line. Results are printed and written to
data/results/<name>.csv so the README and the slide deck can quote them.
Run from the repository root: python src/run_sql.py [sql/analysis.sql] [data/doordash.db]
"""
import os
import re
import sqlite3
import sys

import pandas as pd

SQL_FILE = sys.argv[1] if len(sys.argv) > 1 else "sql/analysis.sql"
DB_FILE = sys.argv[2] if len(sys.argv) > 2 else "data/doordash.db"
OUT_DIR = "data/results"


def queries(sql_text):
    """Yield (name, query) for every block that carries a '-- name:' line."""
    for block in re.split(r"\n(?=-- Q\d)", sql_text):
        match = re.search(r"-- name: (\w+)", block)
        if match:
            yield match.group(1), block


def main():
    pd.set_option("display.width", 200)
    os.makedirs(OUT_DIR, exist_ok=True)
    con = sqlite3.connect(DB_FILE)
    for name, query in queries(open(SQL_FILE, encoding="utf-8").read()):
        result = pd.read_sql(query, con)
        result.to_csv(f"{OUT_DIR}/{name}.csv", index=False)
        print(f"\n== {name}\n{result.to_string(index=False)}")
    con.close()


if __name__ == "__main__":
    main()
