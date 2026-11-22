-- Adds the admin flag used by the /admin dashboard.
-- schema.sql already includes it for fresh databases; run this once on an existing one:
--   docker compose exec -T db psql -U postgres -d sockcheck -v ON_ERROR_STOP=1 < Data_Manipulation_Pipeline/migrations/002_admin_flag.sql
--
-- Then promote an account (there is intentionally no API for this):
--   docker compose exec db psql -U postgres -d sockcheck -c "UPDATE users SET is_admin = TRUE WHERE user_email = 'you@example.com'"
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;
