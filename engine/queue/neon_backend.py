"""Neon Postgres backend for the idea queue (JSONB-document rows).
Mirrors the json_backend contract. No connection is opened at import time."""
import psycopg
from psycopg.types.json import Jsonb
from datetime import datetime, timezone
from engine.config import DATABASE_URL, MIN_VIRAL_SCORE


def _conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)
