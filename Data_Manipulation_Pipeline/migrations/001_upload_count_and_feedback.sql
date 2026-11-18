-- Adds a per-user upload counter and text feedback on past inferences.
-- schema.sql already includes these for fresh databases; run this once on an existing one:
--   docker compose exec -T db psql -U postgres -d sockcheck -v ON_ERROR_STOP=1 < Data_Manipulation_Pipeline/migrations/001_upload_count_and_feedback.sql
BEGIN;

-- Lifetime count of successful /predict uploads; not decremented when history entries are deleted
ALTER TABLE users ADD COLUMN IF NOT EXISTS upload_count INTEGER NOT NULL DEFAULT 0;

-- Backfill from the uploads still on record (a lower bound: deleted entries can't be recovered)
UPDATE users AS u
SET upload_count = counts.n
FROM (SELECT user_id, COUNT(*) AS n FROM user_images GROUP BY user_id) AS counts
WHERE counts.user_id = u.user_id AND u.upload_count < counts.n;

-- One editable piece of feedback per inference
CREATE TABLE IF NOT EXISTS inference_feedback (
    feedback_id   SERIAL PRIMARY KEY,
    inference_id  INTEGER NOT NULL UNIQUE REFERENCES past_inference (inference_id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    feedback_text TEXT NOT NULL CHECK (char_length(feedback_text) BETWEEN 1 AND 2000),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inference_feedback_user_id ON inference_feedback (user_id);

COMMIT;
