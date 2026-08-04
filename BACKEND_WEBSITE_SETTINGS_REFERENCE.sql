-- Build 16.1.0 backend reference migration (apply only if the Railway backend uses PostgreSQL)
-- The uploaded artifact does not contain the Railway backend source. This migration documents
-- the persistence shape expected by the expanded dashboard without exposing private values.

CREATE TABLE IF NOT EXISTS website_settings (
  id BIGSERIAL PRIMARY KEY,
  setting_key TEXT NOT NULL UNIQUE,
  setting_value JSONB NOT NULL DEFAULT '{}'::jsonb,
  category TEXT NOT NULL DEFAULT 'general',
  data_type TEXT NOT NULL DEFAULT 'json',
  is_public BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by BIGINT NULL
);

CREATE INDEX IF NOT EXISTS website_settings_public_idx ON website_settings (is_public, category);

-- Recommended single-document row for the complete dashboard payload:
INSERT INTO website_settings (setting_key, setting_value, category, data_type, is_public)
VALUES ('website_settings_v2', '{}'::jsonb, 'website', 'json', TRUE)
ON CONFLICT (setting_key) DO NOTHING;
