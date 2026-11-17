"""PostgreSQL connection helpers for PulseIQ."""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)


def get_database_settings():
    required_settings = [
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ]

    settings = {
        key: os.getenv(key)
        for key in required_settings
    }

    try:
        import streamlit as st

        for key in required_settings:
            if not settings[key]:
                settings[key] = st.secrets.get(key)

    except Exception:
        pass

    missing = [
        key for key, value in settings.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing PostgreSQL settings: "
            + ", ".join(missing)
            + ". Configure them in .env or Streamlit Cloud Secrets."
        )

    return settings


def get_connection():
    """Open and return a PostgreSQL connection."""

    settings = get_database_settings()

    return psycopg.connect(
        dbname=settings["POSTGRES_DB"],
        user=settings["POSTGRES_USER"],
        password=settings["POSTGRES_PASSWORD"],
        host=settings["POSTGRES_HOST"],
        port=int(settings["POSTGRES_PORT"]),
        connect_timeout=10,
    )


@contextmanager
def database_connection():
    """Provide a connection and close it reliably."""

    connection = get_connection()

    try:
        yield connection
    finally:
        connection.close()
