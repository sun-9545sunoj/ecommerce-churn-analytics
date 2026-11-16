"""Central configuration: paths, dates and database connection."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_RAW = ROOT / "data" / "raw"
DATA_EXPORTS = ROOT / "data" / "exports"
SQL_DIR = ROOT / "sql"
MODELS_DIR = ROOT / "models"
IMAGES_DIR = ROOT / "images"

for _p in (DATA_RAW, DATA_EXPORTS, MODELS_DIR, IMAGES_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# Simulation window
START_DATE = date(2024, 1, 1)
END_DATE = date(2026, 9, 30)

# Churn definition: features use behaviour up to SNAPSHOT_DATE;
# a customer has churned if they place no order in the following CHURN_WINDOW_DAYS.
SNAPSHOT_DATE = date(2026, 6, 30)
CHURN_WINDOW_DAYS = 90

RANDOM_SEED = 42


def pg_url() -> str:
    user = os.getenv("PG_USER", os.getenv("USER", "postgres"))
    password = os.getenv("PG_PASSWORD", "")
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DB", "ecommerce")
    auth = f"{user}:{password}" if password else user
    return f"postgresql+psycopg://{auth}@{host}:{port}/{db}"


def get_engine():
    from sqlalchemy import create_engine

    return create_engine(pg_url(), future=True)
