// Test harness: boots the real Express app on an ephemeral port against a
// throwaway SQLite database, and hands tests a cookie-aware HTTP client.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after } from 'node:test';

process.env.NODE_ENV = 'test';
process.env.RATE_LIMIT_MAX = '100000';

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexora-shop-test-'));
process.env.DATABASE_PATH = path.join(tmpDir, 'test.db');

const { createApp } = await import('../../backend/app.js');
const { seedTestData } = await import('./seedTestData.js');

export const app = await createApp();
await seedTestData();

export const server = app.listen(0, '127.0.0.1');
await new Promise((resolve) => {
  if (server.listening) resolve();
  else server.once('listening', resolve);
});
const { port } = server.address();
export const baseUrl = `http://127.0.0.1:${port}`;

/**
 * Cookie-aware client. Mirrors how a browser talks to the app: HttpOnly session
 * cookie is stored and replayed automatically.
 */
export function createClient() {
  let cookie = '';

  async function call(method, route, body, headers = {}) {
    const init = { method, headers: { accept: 'application/json', ...headers } };
    if (cookie) init.headers.cookie = cookie;
    if (body !== undefined) {
      init.headers['content-type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const response = await fetch(`${baseUrl}${route}`, init);
    const setCookie = response.headers.get('set-cookie');
    if (setCookie) cookie = setCookie.split(';')[0];
    return response;
  }

  return {
    get rawCookie() { return cookie; },
    set rawCookie(value) { cookie = value || ''; },
    call,
    async request(method, route, body, headers) {
      const response = await call(method, route, body, headers);
      const text = await response.text();
      let payload = null;
      try {
        payload = text ? JSON.parse(text) : null;
      } catch {
        payload = text;
      }
      return { status: response.status, headers: response.headers, body: payload };
    },
    get(route) { return this.request('GET', route); },
    post(route, body) { return this.request('POST', route, body); },
    patch(route, body) { return this.request('PATCH', route, body); },
    delete(route) { return this.request('DELETE', route); },
    async register(overrides = {}) {
      const email = overrides.email || `user${Math.random().toString(36).slice(2, 9)}@example.com`;
      return this.post('/api/auth/register', {
        name: 'Test Customer',
        email,
        password: 'Password123',
        ...overrides,
        email,
      });
    },
    async loginAs(email, password) {
      return this.post('/api/auth/login', { email, password });
    },
  };
}

after(() => {
  server.close();
  try {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  } catch {
    // best-effort cleanup of the temp database
  }
});
