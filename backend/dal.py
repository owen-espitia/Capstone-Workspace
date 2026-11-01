import math
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


_ENV_FILE = Path(__file__).with_name(".env")
_VECTOR_DIMENSIONS = 512


def _connect() -> psycopg.Connection[dict[str, Any]]:
    load_dotenv(_ENV_FILE)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(f"DATABASE_URL is not set in the environment or {_ENV_FILE}")

    connection = psycopg.connect(database_url, row_factory=dict_row)
    register_vector(connection)
    return connection


def _validated_embedding(embedding: Iterable[float]) -> list[float]:
    values = [float(value) for value in embedding]
    if len(values) != _VECTOR_DIMENSIONS:
        raise ValueError(
            f"Expected an embedding with {_VECTOR_DIMENSIONS} dimensions, got {len(values)}"
        )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Embedding values must all be finite numbers")
    return values


def search_catalog(
    embedding: Iterable[float],
    limit: int = 5,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Return closest catalog images, ordered by cosine similarity."""
    vector = _validated_embedding(embedding)
    if limit < 1:
        raise ValueError("limit must be at least 1")

    query = """
        SELECT i.image_id, i.image_url, i.category,
               1 - (latest.embedding <=> %s) AS similarity
        FROM images AS i
        JOIN LATERAL (
            SELECT e.embedding
            FROM embeddings AS e
            WHERE e.image_id = i.image_id
            ORDER BY e.embedding_id DESC
            LIMIT 1
        ) AS latest ON TRUE
    """
    pgvector_value = Vector(vector)
    params: list[Any] = [pgvector_value]
    if category is not None:
        query += " WHERE i.category = %s"
        params.append(category)
    query += " ORDER BY latest.embedding <=> %s LIMIT %s"
    params.extend((pgvector_value, limit))

    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())

class UserExistsError(Exception):
    pass


def create_user_pg(user_name: str, user_email: str, password: str) -> dict[str, Any]:
    """Create a user; password is hashed by PostgreSQL pgcrypto (bcrypt).

    Raises UserExistsError if the email is already registered.
    """
    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (user_name, user_email, password_hash)
                    VALUES (%s, %s, crypt(%s, gen_salt('bf')))
                    RETURNING user_id, user_name, user_email
                    """,
                    (user_name, user_email, password),
                )
                return cursor.fetchone()
    except psycopg.errors.UniqueViolation:
        raise UserExistsError("Email already registered")


def verify_user_pg(user_email: str, password: str) -> dict[str, Any] | None:
    """Return the user record if credentials are valid, otherwise None.

    Comparison is done entirely in PostgreSQL using pgcrypto crypt().
    """
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, user_name, user_email
                FROM users
                WHERE user_email = %s
                  AND password_hash = crypt(%s, password_hash)
                """,
                (user_email, password),
            )
            return cursor.fetchone()


def create_user(user_name: str, user_email: str, password_hash: str) -> int:
    """Create a user using a precomputed password hash, returning the user ID."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (user_name, user_email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING user_id
                """,
                (user_name, user_email, password_hash),
            )
            return cursor.fetchone()["user_id"]


def get_user_by_email(user_email: str) -> dict[str, Any] | None:
    """Fetch a user record by email, including its password hash for verification."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, user_name, user_email, password_hash
                FROM users
                WHERE user_email = %s
                """,
                (user_email,),
            )
            return cursor.fetchone()
