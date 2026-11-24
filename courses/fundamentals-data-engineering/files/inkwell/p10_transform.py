"""Project 10: a transformation pipeline, the way dbt and similar tools work, in about 100 lines.

Each file in models/ is one SELECT that becomes one table in the warehouse (warehouse.duckdb):

  stg_*    staging: clean the raw data (types, latest version, duplicates out). One per source table.
  dim_*    dimensions: who, what, when.
  fct_*    facts: what happened, at a clear grain.
  mart_*   what people use: one table per question.

A line "-- depends_on: a, b" says which models must be built first; the runner sorts them (a DAG).
A line "-- materialized: incremental, unique_key: x" adds only new rows instead of rebuilding the table.
Each file in tests/ is a SELECT that must return NO rows. If any test returns rows, the run fails, and the
mart tables are left as they were (we build into a staging schema and publish only when every test passes:
"write, audit, publish").

Run:  python p10_transform.py
"""
import re
import sys
from graphlib import TopologicalSorter

import duckdb

from common import HERE, LAKE, WAREHOUSE, Timer, log, need

MODELS = HERE / "models"
TESTS = HERE / "tests"
RAW = LAKE / "raw"


def read_models() -> dict:
    models = {}
    for f in sorted(MODELS.glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        deps = re.search(r"--\s*depends_on:\s*(.+)", sql)
        mat = re.search(r"--\s*materialized:\s*incremental,\s*unique_key:\s*(\w+)", sql)
        sql = re.sub(r"\{raw:(\w+)\}",
                     lambda m: f"read_parquet('{(RAW / m.group(1)).as_posix()}/*/*.parquet', union_by_name = true)", sql)
        models[f.stem] = {"sql": sql, "deps": [d.strip() for d in deps.group(1).split(",")] if deps else [],
                          "incremental_key": mat.group(1) if mat else None}
    return models


def build(con, name: str, model: dict, schema: str) -> int:
    body = re.sub(r"^\s*--.*$", "", model["sql"], flags=re.M).strip().rstrip(";")
    key = model["incremental_key"]
    if key:
        # Incremental: main.<name> keeps everything stored so far. We only stage the NEW rows here, and
        # show "old + new" under the model's name, so later models and tests see the full table.
        con.execute(f"CREATE TABLE IF NOT EXISTS main.{name} AS SELECT * FROM ({body}) WHERE false")
        con.execute(f"""CREATE OR REPLACE TABLE {schema}.{name}__new AS SELECT * FROM ({body}) new
                        WHERE new.{key} NOT IN (SELECT {key} FROM main.{name})""")
        con.execute(f"CREATE OR REPLACE VIEW {schema}.{name} AS SELECT * FROM main.{name} UNION ALL SELECT * FROM {schema}.{name}__new")
        return con.execute(f"SELECT count(*) FROM {schema}.{name}__new").fetchone()[0]
    con.execute(f"CREATE OR REPLACE TABLE {schema}.{name} AS {body}")
    return con.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]


if __name__ == "__main__":
    need(RAW / "orders", "p07_ingest.py")
    models = read_models()
    order = list(TopologicalSorter({n: m["deps"] for n, m in models.items()}).static_order())
    con = duckdb.connect(str(WAREHOUSE))
    con.execute("CREATE SCHEMA IF NOT EXISTS staging")
    con.execute("SET search_path = 'staging,main'")      # models find each other in staging first

    print("WRITE: building every model into the 'staging' schema")
    for name in order:
        with Timer() as t:
            rows = build(con, name, models[name], "staging")
        kind = "incremental, new rows" if models[name]["incremental_key"] else "rows"
        print(f"  {name:22} {rows:6} {kind:22} {t.ms:6.0f} ms")

    print("AUDIT: running the data tests")
    failed = []
    for f in sorted(TESTS.glob("*.sql")):
        bad = con.execute(f.read_text(encoding="utf-8")).fetchall()
        print(f"  {'PASS' if not bad else 'FAIL'}  {f.stem}" + (f"  ({len(bad)} bad rows, e.g. {bad[0]})" if bad else ""))
        if bad:
            failed.append(f.stem)
    if failed:
        log("p10", "tests failed, nothing published", failed=",".join(failed))
        sys.exit(1)

    print("PUBLISH: every test passed, copying tables to the main schema")
    con.execute("SET search_path = 'main'")
    for name in order:
        if models[name]["incremental_key"]:
            con.execute(f"INSERT INTO main.{name} SELECT * FROM staging.{name}__new")
        else:
            con.execute(f"CREATE OR REPLACE TABLE main.{name} AS SELECT * FROM staging.{name}")
    con.execute("DROP SCHEMA staging CASCADE")
    log("p10", "warehouse built", models=len(order), tests=len(list(TESTS.glob('*.sql'))))
    for row in con.execute("SELECT * FROM mart_daily_sales ORDER BY day DESC LIMIT 3").fetchall():
        print("  ", row)
