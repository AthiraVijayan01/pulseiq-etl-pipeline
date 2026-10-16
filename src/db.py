
"""PostgreSQL connection helpers for PulseIQ."""

import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

# Load local settings from the project's .env file.
load_dotenv()


def get_connection():
    """Open and return a PostgreSQL connection."""
    required_settings = [
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ]

    missing = [
        setting for setting in required_settings
        if not os.getenv(setting)
    ]

    if missing:
        raise RuntimeError(
            "Missing PostgreSQL settings in .env: "
            + ", ".join(missing)
        )

    return psycopg.connect(
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        connect_timeout=5,
    )


@contextmanager
def database_connection():
    """Provide a connection and close it reliably."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
