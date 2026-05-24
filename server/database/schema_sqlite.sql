-- PRIIS SQLite schema — matches priis.ts type definitions exactly
-- Run: sqlite3 server/priis.db < server/database/schema_sqlite.sql

CREATE TABLE IF NOT EXISTS agencies (
    id   TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendors (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    risk REAL DEFAULT 0,
    tier TEXT DEFAULT 'T4'
);

CREATE TABLE IF NOT EXISTS sites (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    kind                TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lng                 REAL NOT NULL,
    sensitive           INTEGER DEFAULT 0,
    infrastructure_class TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
    id                  TEXT PRIMARY KEY,
    agency              TEXT NOT NULL,
    vendor              TEXT NOT NULL,
    site                TEXT,
    amount              REAL NOT NULL,
    signed              TEXT NOT NULL,
    status              TEXT DEFAULT 'unknown',
    tier                TEXT DEFAULT 'T4',
    note                TEXT,
    procurement_method  TEXT DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS events (
    id      TEXT PRIMARY KEY,
    kind    TEXT NOT NULL,
    at      TEXT NOT NULL,
    site_id TEXT,
    ref_id  TEXT,
    label   TEXT NOT NULL,
    tier    TEXT
);

CREATE TABLE IF NOT EXISTS anomalies (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,
    score           REAL NOT NULL,
    band            TEXT NOT NULL,
    site_id         TEXT,
    summary         TEXT NOT NULL,
    factors         TEXT,        -- JSON array of AnomalyFactor
    contracts       TEXT,        -- JSON array of contract IDs
    event_ids       TEXT,        -- JSON array of event IDs
    confidence      INTEGER DEFAULT 1,
    contradictions  TEXT         -- JSON array of strings
);

CREATE TABLE IF NOT EXISTS sources (
    id     TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    tier   TEXT DEFAULT 'T4',
    kind   TEXT NOT NULL,
    status TEXT DEFAULT 'offline'
);

CREATE TABLE IF NOT EXISTS investigations (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    active_vector  TEXT NOT NULL,
    status         TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS alerts (
    id             TEXT PRIMARY KEY,
    at             TEXT NOT NULL,
    kind           TEXT NOT NULL,
    title          TEXT NOT NULL,
    tier           TEXT NOT NULL,
    investigation  TEXT
);
