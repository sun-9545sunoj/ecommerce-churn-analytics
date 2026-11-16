"""Create the schema, bulk-load raw CSVs into staging, clean into typed tables,
build analytical views, and print the data-quality report.

Run:  python -m src.load_to_postgres
"""
from __future__ import annotations

import csv

import pandas as pd
import psycopg

from src.config import DATA_RAW, SQL_DIR, get_engine

TABLES = ["customers", "products", "orders", "order_items", "support_tickets", "web_sessions"]


def run_sql_file(conn: psycopg.Connection, name: str) -> None:
    conn.execute((SQL_DIR / name).read_text())
    print(f"  ran {name}")


def copy_to_staging(conn: psycopg.Connection, table: str) -> int:
    path = DATA_RAW / f"{table}.csv"
    with open(path, newline="") as fh:
        header = next(csv.reader(fh))
    cols = ", ".join(f'"{c}" TEXT' for c in header)
    conn.execute(f"CREATE TABLE staging.{table} ({cols})")
    with conn.cursor() as cur, cur.copy(f"COPY staging.{table} FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                cp.write(chunk)
    return conn.execute(f"SELECT COUNT(*) FROM staging.{table}").fetchone()[0]


def main() -> None:
    engine = get_engine()
    # psycopg needs the plain libpq URL (without the "+psycopg" dialect suffix)
    dsn = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=False) as conn:
        print("Creating schema...")
        run_sql_file(conn, "01_schema.sql")
        print("Loading raw CSVs into staging...")
        for t in TABLES:
            print(f"  staging.{t:<16} {copy_to_staging(conn, t):>9,} rows")
        print("Cleaning + loading typed tables...")
        run_sql_file(conn, "02_transform.sql")
        print("Building analytical views...")
        run_sql_file(conn, "04_analysis_views.sql")
        run_sql_file(conn, "05_features.sql")
        conn.commit()

    print("\nData-quality report")
    with engine.connect() as c:
        for stmt in (SQL_DIR / "03_data_quality.sql").read_text().split(";"):
            body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
            if body:
                print(pd.read_sql(body, c).to_string(index=False), "\n")


if __name__ == "__main__":
    main()
