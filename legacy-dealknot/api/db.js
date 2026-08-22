const { createClient } = require("@libsql/client");

const client = createClient({
  url: process.env.TURSO_DATABASE_URL || "file:local.db",
  authToken: process.env.TURSO_AUTH_TOKEN,
});

async function init() {
  await client.executeMultiple(`
    CREATE TABLE IF NOT EXISTS brokers (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      email      TEXT    NOT NULL UNIQUE,
      name       TEXT    NOT NULL,
      nickname   TEXT    NOT NULL DEFAULT '',
      password   TEXT    NOT NULL,
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
    CREATE TABLE IF NOT EXISTS buyers (
      id         TEXT    PRIMARY KEY,
      broker_id  INTEGER NOT NULL,
      name       TEXT    NOT NULL,
      phone      TEXT    NOT NULL,
      dial       TEXT    NOT NULL DEFAULT '+1',
      country    TEXT    NOT NULL,
      area       TEXT    NOT NULL,
      type       TEXT    NOT NULL,
      cur        TEXT    NOT NULL,
      min_price  REAL    NOT NULL,
      max_price  REAL    NOT NULL,
      intl       INTEGER NOT NULL DEFAULT 0,
      notes      TEXT    NOT NULL DEFAULT '',
      division   TEXT    NOT NULL DEFAULT 'sales',
      period     TEXT    NOT NULL DEFAULT 'monthly',
      label      TEXT    NOT NULL DEFAULT 'active',
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
    CREATE TABLE IF NOT EXISTS sellers (
      id         TEXT    PRIMARY KEY,
      broker_id  INTEGER NOT NULL,
      name       TEXT    NOT NULL,
      phone      TEXT    NOT NULL,
      dial       TEXT    NOT NULL DEFAULT '+1',
      country    TEXT    NOT NULL,
      area       TEXT    NOT NULL,
      type       TEXT    NOT NULL,
      cur        TEXT    NOT NULL,
      price      REAL    NOT NULL,
      intl       INTEGER NOT NULL DEFAULT 0,
      notes      TEXT    NOT NULL DEFAULT '',
      division   TEXT    NOT NULL DEFAULT 'sales',
      period     TEXT    NOT NULL DEFAULT 'monthly',
      label      TEXT    NOT NULL DEFAULT 'active',
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
    CREATE TABLE IF NOT EXISTS connections (
      match_id   TEXT    NOT NULL,
      broker_id  INTEGER NOT NULL,
      buyer_id   TEXT    NOT NULL,
      seller_id  TEXT    NOT NULL,
      connected  INTEGER NOT NULL DEFAULT 1,
      created_at INTEGER NOT NULL DEFAULT (unixepoch()),
      PRIMARY KEY (match_id, broker_id)
    );
    CREATE TABLE IF NOT EXISTS client_notes (
      id         TEXT    PRIMARY KEY,
      broker_id  INTEGER NOT NULL,
      client_id  TEXT    NOT NULL,
      client_type TEXT   NOT NULL,
      body       TEXT    NOT NULL,
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
  `);
  // Commission table
  await client.execute(`
    CREATE TABLE IF NOT EXISTS commissions (
      id                TEXT    PRIMARY KEY,
      broker_id         INTEGER NOT NULL,
      buyer_name        TEXT    NOT NULL DEFAULT '',
      seller_name       TEXT    NOT NULL DEFAULT '',
      area              TEXT    NOT NULL DEFAULT '',
      property_type     TEXT    NOT NULL DEFAULT '',
      deal_value        REAL    NOT NULL DEFAULT 0,
      commission_percent REAL   NOT NULL DEFAULT 0,
      commission_amount REAL    NOT NULL DEFAULT 0,
      currency          TEXT    NOT NULL DEFAULT 'AED',
      status            TEXT    NOT NULL DEFAULT 'Pending',
      expected_date     TEXT    NOT NULL DEFAULT '',
      received_date     TEXT    NOT NULL DEFAULT '',
      notes             TEXT    NOT NULL DEFAULT '',
      created_at        INTEGER NOT NULL DEFAULT (unixepoch())
    )
  `);

  // Additive migrations for existing DBs
  const migrations = [
    "ALTER TABLE brokers ADD COLUMN nickname TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE buyers  ADD COLUMN division   TEXT    NOT NULL DEFAULT 'sales'",
    "ALTER TABLE buyers  ADD COLUMN period     TEXT    NOT NULL DEFAULT 'monthly'",
    "ALTER TABLE buyers  ADD COLUMN label      TEXT    NOT NULL DEFAULT 'active'",
    "ALTER TABLE buyers  ADD COLUMN radius_km  INTEGER NOT NULL DEFAULT 5",
    "ALTER TABLE buyers  ADD COLUMN referred_by TEXT   NOT NULL DEFAULT ''",
    "ALTER TABLE sellers ADD COLUMN division   TEXT    NOT NULL DEFAULT 'sales'",
    "ALTER TABLE sellers ADD COLUMN period     TEXT    NOT NULL DEFAULT 'monthly'",
    "ALTER TABLE sellers ADD COLUMN label      TEXT    NOT NULL DEFAULT 'active'",
    "ALTER TABLE sellers ADD COLUMN referred_by TEXT   NOT NULL DEFAULT ''",
  ];
  for (const sql of migrations) {
    await client.execute(sql).catch(() => {});
  }

  // Remap old property type IDs to new ones
  // "res" → "res_resale", "com" → "com_resale" (kept as legacy; new entries use villa_*/apt_*)
  const typeMigrations = [
    ["UPDATE buyers  SET type = 'res_resale'  WHERE type = 'res'"],
    ["UPDATE buyers  SET type = 'com_resale'  WHERE type = 'com'"],
    ["UPDATE sellers SET type = 'res_resale'  WHERE type = 'res'"],
    ["UPDATE sellers SET type = 'com_resale'  WHERE type = 'com'"],
  ];
  for (const [sql] of typeMigrations) {
    await client.execute(sql).catch(() => {});
  }
}

module.exports = { client, init };
