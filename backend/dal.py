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

HISTORY_MATCHES = 3


def save_inference(user_id: int, user_image_url: str, matches: list[Mapping[str, Any]]) -> int:
    """Persist one /predict run for a user: the upload plus its top matches.

    Writes past_inference, user_images and inference_results in a single
    transaction and returns the new inference_id.
    """
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO past_inference DEFAULT VALUES RETURNING inference_id")
            inference_id = cursor.fetchone()["inference_id"]
            cursor.execute(
                "INSERT INTO user_images (user_id, user_image_url, inference_id) VALUES (%s, %s, %s)",
                (user_id, user_image_url, inference_id),
            )
            cursor.executemany(
                """
                INSERT INTO inference_results (inference_id, image_id, rank, similarity)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (inference_id, m["image_id"], rank, float(m["similarity"]))
                    for rank, m in enumerate(matches[:HISTORY_MATCHES], start=1)
                ],
            )
            return inference_id


def get_user_history(user_id: int, limit: int = 24, offset: int = 0) -> list[dict[str, Any]]:
    """Return a user's past uploads (newest first), each with its stored top matches.

    Reads only the stored inference_results rows; no model inference is run.
    """
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ui.user_image_id, ui.user_image_url, pi.inference_id, pi.created_at
                FROM user_images AS ui
                JOIN past_inference AS pi ON pi.inference_id = ui.inference_id
                WHERE ui.user_id = %s
                ORDER BY pi.created_at DESC, ui.user_image_id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            items = list(cursor.fetchall())
            if not items:
                return []

            cursor.execute(
                """
                SELECT r.inference_id, r.rank, r.similarity,
                       i.image_id, i.image_url, i.category
                FROM inference_results AS r
                JOIN images AS i ON i.image_id = r.image_id
                WHERE r.inference_id = ANY(%s) AND r.rank <= %s
                ORDER BY r.inference_id, r.rank
                """,
                ([item["inference_id"] for item in items], HISTORY_MATCHES),
            )
            by_inference: dict[int, list[dict[str, Any]]] = {}
            for row in cursor.fetchall():
                by_inference.setdefault(row["inference_id"], []).append(row)

    for item in items:
        item["matches"] = by_inference.get(item["inference_id"], [])
    return items


def delete_inference(user_id: int, inference_id: int) -> list[str] | None:
    """Delete one of a user's history entries (upload row, inference and its results).

    Returns the stored filenames of the removed uploads so the caller can delete the
    files, or None if the inference doesn't exist or belongs to someone else.
    """
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM user_images
                WHERE inference_id = %s AND user_id = %s
                RETURNING user_image_url
                """,
                (inference_id, user_id),
            )
            filenames = [row["user_image_url"] for row in cursor.fetchall()]
            if not filenames:
                return None
            # inference_results rows go with it (ON DELETE CASCADE)
            cursor.execute("DELETE FROM past_inference WHERE inference_id = %s", (inference_id,))
            return filenames


def user_owns_image(user_id: int, user_image_url: str) -> bool:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM user_images WHERE user_id = %s AND user_image_url = %s",
                (user_id, user_image_url),
            )
            return cursor.fetchone() is not None


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
