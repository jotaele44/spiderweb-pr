-- NEW reconstruction schema for recovered Floot Spiderweb endpoint regression.
-- Derived from helpers/schema.tsx and endpoint query requirements.
-- It is NOT asserted to be historical DDL and intentionally omits unproven
-- foreign keys, uniqueness constraints, indexes, triggers, and cascades.

DROP TABLE IF EXISTS spatial_layer_acl, spatial_layer_features, spatial_layers, spatial_audit_log, spatial_investigations, login_attempts, sessions, user_passwords, users CASCADE;

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  display_name TEXT NOT NULL,
  avatar_url TEXT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NULL DEFAULT now()
);
CREATE TABLE user_passwords (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NULL DEFAULT now()
);
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at TIMESTAMPTZ NULL DEFAULT now(),
  last_accessed TIMESTAMPTZ NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE login_attempts (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  attempted_at TIMESTAMPTZ NULL DEFAULT now(),
  success BOOLEAN NULL DEFAULT false
);
CREATE TABLE spatial_audit_log (
  id BIGSERIAL PRIMARY KEY,
  actor_user_id INTEGER NULL,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  workspace_key TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE spatial_investigations (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  spatial_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  graph_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  query_context TEXT NOT NULL DEFAULT '',
  anomaly_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE spatial_layers (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL,
  workspace_key TEXT NOT NULL,
  name TEXT NOT NULL,
  format TEXT NOT NULL,
  source_uri TEXT NULL,
  source_manifestation_sha256 TEXT NULL,
  logical_sha256 TEXT NOT NULL,
  crs TEXT NOT NULL DEFAULT 'EPSG:4326',
  feature_count INTEGER NOT NULL,
  rejected_count INTEGER NOT NULL DEFAULT 0,
  min_lon DOUBLE PRECISION NULL,
  min_lat DOUBLE PRECISION NULL,
  max_lon DOUBLE PRECISION NULL,
  max_lat DOUBLE PRECISION NULL,
  temporal_field TEXT NULL,
  temporal_min TIMESTAMPTZ NULL,
  temporal_max TIMESTAMPTZ NULL,
  style JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE spatial_layer_features (
  id BIGSERIAL PRIMARY KEY,
  layer_id TEXT NOT NULL,
  feature_id TEXT NOT NULL,
  geometry_type TEXT NOT NULL,
  geometry JSONB NOT NULL,
  properties JSONB NOT NULL DEFAULT '{}'::jsonb,
  min_lon DOUBLE PRECISION NOT NULL,
  min_lat DOUBLE PRECISION NOT NULL,
  max_lon DOUBLE PRECISION NOT NULL,
  max_lat DOUBLE PRECISION NOT NULL,
  observed_at TIMESTAMPTZ NULL
);
CREATE TABLE spatial_layer_acl (
  id BIGSERIAL PRIMARY KEY,
  layer_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  created_by_user_id INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);