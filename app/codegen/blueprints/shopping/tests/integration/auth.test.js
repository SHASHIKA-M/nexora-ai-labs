import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient, baseUrl, app } from '../helpers/harness.js';
import { FIXTURES } from '../helpers/seedTestData.js';

test('health endpoint reports a live, seeded database', async () => {
  const client = createClient();
  const { status, body } = await client.get('/api/health');
  assert.equal(status, 200);
  assert.equal(body.status, 'ok');
  assert.ok(body.product_count >= 4);
});

test('registration creates an account, signs the user in and never leaks the hash', async () => {
  const client = createClient();
  const { status, body } = await client.register({ email: 'newperson@example.com' });
  assert.equal(status, 201);
  assert.equal(body.user.email, 'newperson@example.com');
  assert.equal(body.user.role, 'customer');
  assert.ok(body.token);
  assert.equal(body.user.password_hash, undefined);

  const me = await client.get('/api/auth/me');
  assert.equal(me.body.user.email, 'newperson@example.com');
});

test('duplicate registration is rejected with 409', async () => {
  const client = createClient();
  await client.register({ email: 'dupe@example.com' });
  const second = await client.register({ email: 'dupe@example.com' });
  assert.equal(second.status, 409);
});

test('registration validates email and password strength', async () => {
  const client = createClient();
  assert.equal((await client.post('/api/auth/register', { name: 'X', email: 'bad', password: 'Password123' })).status, 422);
  assert.equal((await client.post('/api/auth/register', { name: 'X Y', email: 'ok@example.com', password: 'weak' })).status, 422);
});

test('login succeeds with correct credentials and fails with wrong ones', async () => {
  const client = createClient();
  const good = await client.loginAs(FIXTURES.customer.email, FIXTURES.customer.password);
  assert.equal(good.status, 200);
  assert.equal(good.body.user.email, FIXTURES.customer.email);

  const bad = await createClient().loginAs(FIXTURES.customer.email, 'WrongPassword1');
  assert.equal(bad.status, 401);
});

test('unknown accounts and wrong passwords return the same error', async () => {
  const unknown = await createClient().loginAs('ghost@example.com', 'Password123');
  const wrong = await createClient().loginAs(FIXTURES.customer.email, 'Password123');
  assert.equal(unknown.status, 401);
  assert.equal(wrong.status, 401);
  assert.equal(unknown.body.error, wrong.body.error);
});

test('logout destroys the session', async () => {
  const client = createClient();
  await client.loginAs(FIXTURES.customer.email, FIXTURES.customer.password);
  await client.post('/api/auth/logout', {});
  const me = await client.get('/api/auth/me');
  assert.equal(me.body.user, null);
});

test('protected endpoints reject anonymous requests with 401', async () => {
  const client = createClient();
  assert.equal((await client.get('/api/cart')).status, 401);
  assert.equal((await client.get('/api/orders')).status, 401);
  assert.equal((await client.get('/api/admin/stats')).status, 401);
});

test('admin endpoints reject non-admin sessions with 403', async () => {
  const client = createClient();
  await client.loginAs(FIXTURES.customer.email, FIXTURES.customer.password);
  const result = await client.get('/api/admin/stats');
  assert.equal(result.status, 403);
});

test('security headers and CSRF protection are applied', async () => {
  const response = await fetch(`${baseUrl}/api/health`);
  assert.ok(response.headers.get('content-security-policy')?.includes("default-src 'self'"));
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('x-powered-by'), null);

  const crossSite = await createClient().call('POST', '/api/auth/login',
    { email: FIXTURES.customer.email, password: FIXTURES.customer.password },
    { origin: 'https://evil.example' });
  assert.equal(crossSite.status, 403);
});

test('the SPA shell and static assets are served', async () => {
  const shell = await fetch(`${baseUrl}/`);
  assert.equal(shell.status, 200);
  const shellHtml = await shell.text();
  // The brand is personalised per generated project, so assert on structure
  // rather than on any one client's trading name.
  assert.match(shellHtml, /id="view"/);
  assert.match(shellHtml, /src="assets\/app\.js"/);
  assert.match(shellHtml, /<title>[^<]+<\/title>/);

  const asset = await fetch(`${baseUrl}/products/aurora-linen-shirt.svg`);
  assert.equal(asset.status, 200);
  assert.match(asset.headers.get('content-type') || '', /svg/);

  const missingApi = await fetch(`${baseUrl}/api/does-not-exist`);
  assert.equal(missingApi.status, 404);

  const bundle = await fetch(`${baseUrl}/assets/app.js`);
  assert.equal(bundle.status, 200);
  assert.match(bundle.headers.get('content-type') || '', /javascript/);

  // The shell references a stylesheet that must actually exist, otherwise the
  // storefront ships unstyled.
  const stylesheetRef = shellHtml.match(/href="(assets\/styles\.css)"/);
  assert.ok(stylesheetRef, 'index.html links the compiled stylesheet');
  const stylesheet = await fetch(`${baseUrl}/${stylesheetRef[1]}`);
  assert.equal(stylesheet.status, 200);
  assert.match(await stylesheet.text(), /--gold/);
});

test('app instance is mounted for direct inspection', () => {
  assert.ok(app);
});
