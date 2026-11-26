// Session-based authentication with hashed opaque tokens, HttpOnly cookies and
// bearer-token support for API clients and automated tests.
import { createHash, randomBytes } from 'node:crypto';
import { execute, queryOne } from '../../database/db.js';
import { HttpError } from '../lib/validate.js';

const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME || 'nexora_shop_session';
const SESSION_DAYS = Number(process.env.SESSION_DAYS || 7);

function tokenHash(token) {
  return createHash('sha256').update(token).digest('hex');
}

function parseCookies(header = '') {
  return Object.fromEntries(
    header
      .split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const index = part.indexOf('=');
        return index === -1 ? [part, ''] : [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
      }),
  );
}

export function extractToken(req) {
  const authorization = req.get('authorization') || '';
  if (authorization.toLowerCase().startsWith('bearer ')) {
    return authorization.slice(7).trim();
  }
  return parseCookies(req.get('cookie') || '')[SESSION_COOKIE] || null;
}

export async function createSession(userId) {
  const token = randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000);
  const id = randomBytes(12).toString('hex');
  await execute(
    'INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?)',
    id, userId, tokenHash(token), expiresAt.toISOString(),
  );
  await execute('DELETE FROM sessions WHERE expires_at < ?', new Date().toISOString());
  return { token, id, expiresAt };
}

export function sessionCookie(token, expiresAt) {
  const secure = process.env.COOKIE_SECURE === 'true' ? '; Secure' : '';
  return `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Expires=${expiresAt.toUTCString()}${secure}`;
}

export function clearCookie() {
  return `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}

export async function destroySession(token) {
  if (!token) return;
  await execute('DELETE FROM sessions WHERE token_hash = ?', tokenHash(token));
}

export async function resolveUser(req) {
  const token = extractToken(req);
  if (!token) return null;
  const row = await queryOne(
    `SELECT s.id AS session_id, s.expires_at, u.id, u.name, u.email, u.role
       FROM sessions s JOIN users u ON u.id = s.user_id
      WHERE s.token_hash = ? AND u.is_active = 1`,
    tokenHash(token),
  );
  if (!row) return null;
  if (new Date(row.expires_at).getTime() < Date.now()) {
    await execute('DELETE FROM sessions WHERE id = ?', row.session_id);
    return null;
  }
  return { id: row.id, name: row.name, email: row.email, role: row.role, sessionId: row.session_id };
}

export function attachUser() {
  return async (req, _res, next) => {
    try {
      req.user = await resolveUser(req);
      next();
    } catch (error) {
      next(error);
    }
  };
}

export function requireAuth(req, _res, next) {
  if (!req.user) return next(new HttpError(401, 'Sign in to continue.'));
  return next();
}

export function requireAdmin(req, _res, next) {
  if (!req.user) return next(new HttpError(401, 'Sign in to continue.'));
  if (req.user.role !== 'admin') return next(new HttpError(403, 'Administrator access is required.'));
  return next();
}
