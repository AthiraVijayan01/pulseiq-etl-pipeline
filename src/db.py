
"""PostgreSQL connection helpers for PulseIQ."""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)


def get_secret(key, default=None):
    """Read settings from environment variables or Streamlit secrets."""

    value = os.getenv(key)

    if value:
        return value

    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


def get_database_settings():
    """Read Docker or Neon PostgreSQL settings."""

    mode = get_secret("DATABASE_MODE", "docker").lower()

    if mode == "neon":
        database_url = (
            get_secret("NEON_DATABASE_URL")
            or get_secret("DATABASE_URL")
        )

        if not database_url:
            raise RuntimeError(
                "Configure NEON_DATABASE_URL or DATABASE_URL."
            )

        if not database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise RuntimeError("Invalid PostgreSQL database URL.")

        return {
            "mode": "neon",
            "database_url": database_url,
        }

    if mode != "docker":
        raise RuntimeError(
            "DATABASE_MODE must be either 'docker' or 'neon'."
        )

    required_settings = [
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ]

    settings = {
        key: get_secret(key)
        for key in required_settings
    }

    missing = [
        key for key, value in settings.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing PostgreSQL settings: "
            + ", ".join(missing)
        )

    return {
        "mode": "docker",
        **settings,
        "POSTGRES_SSLMODE": get_secret(
            "POSTGRES_SSLMODE", "disable"
        ),
    }


def get_connection():
    """Open and return a PostgreSQL connection."""

    settings = get_database_settings()

    if settings["mode"] == "neon":
        return psycopg.connect(
            settings["database_url"],
            connect_timeout=10,
        )

    return psycopg.connect(
        dbname=settings["POSTGRES_DB"],
        user=settings["POSTGRES_USER"],
        password=settings["POSTGRES_PASSWORD"],
        host=settings["POSTGRES_HOST"],
        port=int(settings["POSTGRES_PORT"]),
        sslmode=settings["POSTGRES_SSLMODE"],
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
