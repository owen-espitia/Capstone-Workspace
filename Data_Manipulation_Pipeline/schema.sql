CREATE EXTENSION IF NOT EXISTS vector;

-- One row per garment crop (what you embed) — category lives here, not on Embeddings
CREATE TABLE images (
    image_id  SERIAL PRIMARY KEY,
    image_url TEXT NOT NULL,   -- R2 pointer to the catalog crop (local path for now)
    category  TEXT NOT NULL
);
CREATE INDEX idx_images_category ON images (category);

-- Intentionally allows multiple rows per image_id over time (e.g. re-embedding with a newer model)
CREATE TABLE embeddings (
    embedding_id SERIAL PRIMARY KEY,
    image_id     INTEGER NOT NULL REFERENCES images (image_id) ON DELETE CASCADE,
    embedding    VECTOR(512) NOT NULL
);
CREATE INDEX idx_embeddings_image_id ON embeddings (image_id);
CREATE INDEX idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    user_name     TEXT NOT NULL,
    user_email    TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL   -- a hash (bcrypt/argon2), never the raw password
);

CREATE TABLE past_inference (
    inference_id SERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_images (
    user_image_id  SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    user_image_url TEXT NOT NULL,   -- R2 pointer, separate bucket/prefix from `images`
    inference_id   INTEGER REFERENCES past_inference (inference_id) ON DELETE SET NULL
);
CREATE INDEX idx_user_images_user_id ON user_images (user_id);
CREATE INDEX idx_user_images_inference_id ON user_images (inference_id);

-- Replaces img1_Url, img...Url — one row per ranked result, with the score your MVP promises
CREATE TABLE inference_results (
    result_id    SERIAL PRIMARY KEY,
    inference_id INTEGER NOT NULL REFERENCES past_inference (inference_id) ON DELETE CASCADE,
    image_id     INTEGER NOT NULL REFERENCES images (image_id) ON DELETE CASCADE,
    rank         SMALLINT NOT NULL,
    similarity   REAL NOT NULL,
    UNIQUE (inference_id, rank)
);
CREATE INDEX idx_inference_results_inference_id ON inference_results (inference_id);
CREATE INDEX idx_inference_results_image_id ON inference_results (image_id);
