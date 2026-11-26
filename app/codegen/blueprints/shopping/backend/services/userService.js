import { query, queryOne, execute } from '../../database/db.js';
import { HttpError, requireEmail, requireString, requirePassword } from '../lib/validate.js';
import { hashPassword, verifyPassword } from '../lib/passwords.js';

const PUBLIC_USER = 'id, name, email, role, created_at';

export async function registerUser(payload) {
  const name = requireString(payload.name, 'Name', { min: 2, max: 120 });
  const email = requireEmail(payload.email);
  const password = requirePassword(payload.password);
  const existing = await queryOne('SELECT id FROM users WHERE email = ?', email);
  if (existing) throw new HttpError(409, 'An account with that email already exists.');
  const created = await execute(
    'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
    name, email, hashPassword(password), 'customer',
  );
  const user = await queryOne(`SELECT ${PUBLIC_USER} FROM users WHERE id = ?`, Number(created.lastInsertRowid));
  return user;
}

export async function authenticate(payload) {
  const email = requireEmail(payload.email);
  const password = typeof payload.password === 'string' ? payload.password : '';
  const row = await queryOne('SELECT * FROM users WHERE email = ?', email);
  // Always run a hash comparison so response time does not reveal account existence.
  const valid = verifyPassword(password, row?.password_hash ?? 'scrypt$00$00');
  if (!row || !valid) throw new HttpError(401, 'Email or password is incorrect.');
  if (!row.is_active) throw new HttpError(403, 'This account has been disabled.');
  return { id: row.id, name: row.name, email: row.email, role: row.role };
}

export async function listCustomers() {
  return query(
    `SELECT u.id, u.name, u.email, u.role, u.created_at,
            (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count
       FROM users u ORDER BY u.id`,
  );
}
