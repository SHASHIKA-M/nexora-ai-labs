// Database access layer.
//
// Primary driver: the Node.js built-in `node:sqlite` module.
// Fallback driver: the `sqlite3` package (used only when the built-in module is
// unavailable). Both expose the same tiny async wrapper below so services never
// depend on the driver that happened to load.
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, '..');
export const SCHEMA_PATH = path.join(here, 'schema.sql');

let db = null;
let driver = null;

async function openBuiltin(filename) {
  const sqlite = await import('node:sqlite');
  const handle = new sqlite.DatabaseSync(filename);
  handle.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;');
  const statements = new Map();
  const prepare = (sql) => {
    if (!statements.has(sql)) {
      const statement = handle.prepare(sql);
      statements.set(sql, {
        all: (...params) => statement.all(...params),
        get: (...params) => statement.get(...params),
        run: (...params) => statement.run(...params),
      });
    }
    return statements.get(sql);
  };
  return {
    driver: 'node:sqlite',
    exec: (sql) => handle.exec(sql),
    prepare,
    close: () => handle.close(),
  };
}

async function openSqlite3(filename) {
  const mod = await import('sqlite3');
  const sqlite3 = mod.default ?? mod;
  const handle = await new Promise((resolve, reject) => {
    const instance = new sqlite3.Database(filename, (error) => (error ? reject(error) : resolve(instance)));
  });
  await new Promise((resolve, reject) => handle.exec('PRAGMA foreign_keys = ON;', (error) => (error ? reject(error) : resolve())));
  return {
    driver: 'sqlite3',
    exec: (sql) => new Promise((resolve, reject) => handle.exec(sql, (error) => (error ? reject(error) : resolve()))),
    prepare: (sql) => ({
      all: (...params) => new Promise((resolve, reject) => handle.all(sql, params, (error, rows) => (error ? reject(error) : resolve(rows || [])))),
      get: (...params) => new Promise((resolve, reject) => handle.get(sql, params, (error, row) => (error ? reject(error) : resolve(row)))),
      run: (...params) =>
        new Promise((resolve, reject) =>
          handle.run(sql, params, function onDone(error) {
            return error ? reject(error) : resolve({ changes: this.changes, lastInsertRowid: this.lastID });
          })),
    }),
    close: () => new Promise((resolve) => handle.close(() => resolve())),
  };
}

export function databasePath() {
  const configured = process.env.DATABASE_PATH
    || process.env.DATABASE_URL?.replace(/^sqlite:\/\/(\.\/)?/, '');
  if (!configured) return path.join(ROOT, 'data', 'store.db');
  if (configured === ':memory:') return configured;
  return path.isAbsolute(configured) ? configured : path.join(ROOT, configured);
}

export async function getDb() {
  if (db) return db;
  const filename = databasePath();
  if (filename !== ':memory:') fs.mkdirSync(path.dirname(filename), { recursive: true });
  try {
    db = await openBuiltin(filename);
  } catch (builtinError) {
    try {
      db = await openSqlite3(filename);
    } catch (fallbackError) {
      throw new Error(
        `No SQLite driver available. Built-in node:sqlite failed (${builtinError.message}); sqlite3 failed (${fallbackError.message}).`,
      );
    }
  }
  driver = db.driver;
  return db;
}

export function driverName() {
  return driver;
}

export async function closeDb() {
  if (!db) return;
  await db.close();
  db = null;
  driver = null;
}

export async function query(sql, ...params) {
  return (await getDb()).prepare(sql).all(...params);
}

export async function queryOne(sql, ...params) {
  return (await getDb()).prepare(sql).get(...params);
}

export async function execute(sql, ...params) {
  return (await getDb()).prepare(sql).run(...params);
}

export async function withTransaction(fn) {
  const database = await getDb();
  database.exec('BEGIN IMMEDIATE');
  try {
    const result = await fn();
    database.exec('COMMIT');
    return result;
  } catch (error) {
    try {
      database.exec('ROLLBACK');
    } catch {
      // A failed rollback means the transaction already ended; nothing to do.
    }
    throw error;
  }
}

export async function migrate() {
  const database = await getDb();
  database.exec(fs.readFileSync(SCHEMA_PATH, 'utf8'));
  return database;
}
