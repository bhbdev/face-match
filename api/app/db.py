"""Postgres/pgvector access. The schema lives in db/init.sql."""

from typing import Any, Iterable

import numpy as np
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
    configure=register_vector,
    open=False,
)


def open_pool() -> None:
    pool.open(wait=True, timeout=30)


def close_pool() -> None:
    pool.close()


def search(embedding: np.ndarray, limit: int) -> list[dict[str, Any]]:
    """Nearest faces by cosine distance. similarity = 1 - distance (higher is closer)."""
    sql = """
        SELECT id, image_file, crop_file, title, year, author, license, source_url,
               det_score, 1 - (embedding <=> %(q)s) AS similarity
        FROM faces
        ORDER BY embedding <=> %(q)s
        LIMIT %(limit)s
    """
    with pool.connection() as conn:
        return conn.execute(sql, {"q": embedding, "limit": limit}).fetchall()


def stats() -> dict[str, int]:
    with pool.connection() as conn:
        faces = conn.execute("SELECT count(*) AS n FROM faces").fetchone()["n"]
        images = conn.execute("SELECT count(*) AS n FROM indexed_images").fetchone()["n"]
        with_faces = conn.execute(
            "SELECT count(DISTINCT image_file) AS n FROM faces"
        ).fetchone()["n"]
    return {"faces": faces, "images_scanned": images, "images_with_faces": with_faces}


def indexed_image_files() -> set[str]:
    with pool.connection() as conn:
        rows = conn.execute("SELECT image_file FROM indexed_images").fetchall()
    return {r["image_file"] for r in rows}


def insert_image_result(image_file: str, face_rows: Iterable[dict[str, Any]]) -> None:
    """Record one scanned image and its faces atomically."""
    face_rows = list(face_rows)
    with pool.connection() as conn:
        with conn.transaction():
            for row in face_rows:
                conn.execute(
                    """
                    INSERT INTO faces (image_file, face_idx, crop_file, title, year, author,
                                       license, source_url, det_score, bbox, embedding)
                    VALUES (%(image_file)s, %(face_idx)s, %(crop_file)s, %(title)s, %(year)s,
                            %(author)s, %(license)s, %(source_url)s, %(det_score)s,
                            %(bbox)s, %(embedding)s)
                    ON CONFLICT (image_file, face_idx) DO NOTHING
                    """,
                    row,
                )
            conn.execute(
                """
                INSERT INTO indexed_images (image_file, n_faces) VALUES (%s, %s)
                ON CONFLICT (image_file) DO UPDATE
                    SET n_faces = EXCLUDED.n_faces, indexed_at = now()
                """,
                (image_file, len(face_rows)),
            )


def clear_index() -> None:
    with pool.connection() as conn:
        conn.execute("TRUNCATE faces, indexed_images RESTART IDENTITY")
