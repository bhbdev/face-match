-- Runs automatically the first time the Postgres volume is created.
-- ArcFace (InsightFace buffalo_l) embeddings are 512-dimensional.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per face found in a historic photo.
CREATE TABLE IF NOT EXISTS faces (
    id          BIGSERIAL PRIMARY KEY,
    image_file  TEXT        NOT NULL,          -- filename inside data/historic/
    face_idx    INTEGER     NOT NULL,          -- 0 = largest face in the image
    crop_file   TEXT        NOT NULL,          -- filename inside data/crops/
    title       TEXT,
    year        TEXT,                          -- free text, e.g. "circa 1865"
    author      TEXT,
    license     TEXT,
    source_url  TEXT,
    det_score   REAL,
    bbox        REAL[],                        -- x1, y1, x2, y2 in image pixels
    embedding   vector(512) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (image_file, face_idx)
);

-- Cosine distance, matching how ArcFace embeddings are compared.
CREATE INDEX IF NOT EXISTS faces_embedding_hnsw
    ON faces USING hnsw (embedding vector_cosine_ops);

-- Every image the indexer has looked at, including ones with no usable face,
-- so re-running the indexer doesn't redo that work.
CREATE TABLE IF NOT EXISTS indexed_images (
    image_file  TEXT PRIMARY KEY,
    n_faces     INTEGER     NOT NULL DEFAULT 0,
    indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
