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

