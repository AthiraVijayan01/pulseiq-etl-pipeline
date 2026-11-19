
"""PostgreSQL connection helpers for PulseIQ."""

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)


def get_secret(key, default=None):
    """Read Streamlit Cloud secrets first, then environment variables."""

    try:
        import streamlit as st

        value = st.secrets.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    except Exception:
        pass

    value = os.getenv(key)

    if value is not None and value.strip():
        return value.strip()

    return default


def get_database_settings():
    """Read Neon or Docker PostgreSQL settings."""

    database_url = (
        get_secret("NEON_DATABASE_URL")
        or get_secret("DATABASE_URL")
    )

    mode = get_secret("DATABASE_MODE")

    if mode:
        mode = mode.strip().lower()
    elif database_url:
        mode = "neon"
    else:
        mode = "docker"

    if mode == "neon":

        if not database_url:
            raise RuntimeError(
                "Neon mode selected, but NEON_DATABASE_URL "
                "or DATABASE_URL is missing from Streamlit Secrets."
            )

        parsed_url = urlparse(database_url)

        if parsed_url.scheme not in ("postgresql", "postgres"):
            raise RuntimeError(
                "Invalid Neon URL. Expected a PostgreSQL connection URL."
            )

        if not parsed_url.hostname or not parsed_url.path:
            raise RuntimeError(
                "Neon connection URL is incomplete."
            )

        return {
            "mode": "neon",
            "database_url": database_url,
        }

    if mode not in ("docker", "postgres"):
        raise RuntimeError(
            "DATABASE_MODE must be 'neon' or 'docker'."
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
            + ". For Neon, configure DATABASE_MODE='neon' "
            "and NEON_DATABASE_URL in Streamlit Secrets."
        )

    return {
        "mode": "docker",
        **settings,
        "POSTGRES_SSLMODE": get_secret(
            "POSTGRES_SSLMODE", "require"
        ),
    }


def get_connection():
    """Open and return a PostgreSQL connection."""

    settings = get_database_settings()

    if settings["mode"] == "neon":
        return psycopg.connect(
            settings["database_url"],
            sslmode="require",
            connect_timeout=15,
        )

    return psycopg.connect(
        dbname=settings["POSTGRES_DB"],
        user=settings["POSTGRES_USER"],
        password=settings["POSTGRES_PASSWORD"],
        host=settings["POSTGRES_HOST"],
        port=int(settings["POSTGRES_PORT"]),
        sslmode=settings["POSTGRES_SSLMODE"],
        connect_timeout=15,
    )


@contextmanager
def database_connection():
    """Provide a database connection and close it reliably."""

    connection = get_connection()

    try:
        yield connection
    finally:
        connection.close()
