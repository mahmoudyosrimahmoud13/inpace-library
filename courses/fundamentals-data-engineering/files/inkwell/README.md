# Inkwell Books: the course projects

Inkwell Books is a small, made-up online bookshop. Over the course you build its whole data platform, one
stage of the data engineering lifecycle at a time.

## Set up once

1. Install Python 3.9 or newer (python.org).
2. Install DuckDB, the only library the projects need:  `pip install duckdb`
3. Open a terminal in this folder and run:  `python p01_setup_check.py`

## The projects

| Day | Script | What you build |
|---|---|---|
| 1 | `p01_setup_check.py` | Check your setup |
| 2 | `p02_lifecycle.py` | The whole lifecycle in one small file |
| 3 | `p03_decoupled.py` | Loose coupling and planning for failure |
| 4 | `p04_tco.py` | Total cost of ownership of three options |
| 5 | `p05_source_system.py` | The shop's database and website events (the sources) |
| 6 | `p06_storage.py` | CSV, JSON and Parquet compared; a partitioned lake |
| 7 | `p07_ingest.py` | Incremental ingestion, change data capture, dead letters |
| 8 | `p08_queries.py` | Query plans, pruning, a join that multiplies rows, windows |
| 9 | `p09_model.py` | Normalized, star schema (with type 2 history) and one big table |
| 10 | `p10_transform.py` + `models/` + `tests/` | A tested transformation pipeline |
| 11 | `p11_serve.py` | Metrics layer, dashboard, ML features, reverse ETL |
| 12 | `p12_secure.py`, `run_all.py` | Privacy, tested backups, and the whole pipeline on a schedule |

Run them in order: each one uses what the earlier ones made. Everything is written to `inkwell_data/`.
Delete that folder to start again from scratch (then run project 5 before 6 to 12).
