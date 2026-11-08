import sqlite3, re, sys, json, pandas as pd
pd.set_option("display.width", 200)
sql = open(sys.argv[1]).read()
con = sqlite3.connect(sys.argv[2])
out = {}
for block in re.split(r"\n(?=-- Q\d)", sql):
    m = re.search(r"-- name: (\w+)", block)
    if not m: continue
    df = pd.read_sql(block, con)
    out[m.group(1)] = df
    print("\n==", m.group(1)); print(df.to_string(index=False))
