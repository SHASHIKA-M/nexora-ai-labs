import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient } from '../helpers/harness.js';
import { FIXTURES } from '../helpers/seedTestData.js';

async function adminClient() {
  const client = createClient();
  const login = await client.loginAs(FIXTURES.admin.email, FIXTURES.admin.password);
  assert.equal(login.status, 200);
  return client;
}

test('admin order list supports status filters', async () => {
  const admin = await adminClient();
  const all = await admin.get('/api/admin/orders');
  assert.equal(all.status, 200);
  assert.ok(Array.isArray(all.body.orders));
  const filtered = await admin.get('/api/admin/orders?status=delivered');
  assert.ok(filtered.body.orders.every((order) => order.status === 'delivered'));
});

test('admin customer list includes order counts', async () => {
  const admin = await adminClient();
  const { status, body } = await admin.get('/api/admin/customers');
  assert.equal(status, 200);
  assert.ok(body.customers.length >= 2);
  assert.ok(body.customers.every((customer) => typeof customer.order_count === 'number'));
});

test('admin can create a product and update price and stock', async () => {
  const admin = await adminClient();
  const created = await admin.post('/api/admin/products', {
    name: `Studio Tray ${Math.random().toString(36).slice(2, 6)}`,
    price_cents: 4200,
    stock: 7,
    description: 'Machined aluminium tray',
  });
  assert.equal(created.status, 201);
  const id = created.body.product.id;

  const updated = await admin.patch(`/api/admin/products/${id}`, { price_cents: 3900, stock: 12 });
  assert.equal(updated.status, 200);
  assert.equal(updated.body.product.price_cents, 3900);
  assert.equal(updated.body.product.stock, 12);
});

test('admin product validation rejects bad prices and stock', async () => {
  const admin = await adminClient();
  assert.equal((await admin.post('/api/admin/products', { name: 'Bad', price_cents: 0 })).status, 422);
  assert.equal((await admin.post('/api/admin/products', { name: 'Bad', price_cents: 100, stock: -5 })).status, 422);

  const list = await admin.get('/api/admin/products');
  const id = list.body.products[0].id;
  assert.equal((await admin.patch(`/api/admin/products/${id}`, { price_cents: -1 })).status, 422);
});

test('deactivating a product hides it from the public catalogue', async () => {
  const admin = await adminClient();
  const created = await admin.post('/api/admin/products', {
    name: `Hidden Item ${Math.random().toString(36).slice(2, 6)}`,
    price_cents: 1000,
    stock: 5,
  });
  const product = created.body.product;
  await admin.patch(`/api/admin/products/${product.id}`, { is_active: false });

  const publicList = await createClient().get(`/api/products/${product.slug}`);
  assert.equal(publicList.status, 404);

  const adminList = await admin.get('/api/admin/products');
  const stillThere = adminList.body.products.find((item) => item.id === product.id);
  assert.ok(stillThere, 'inactive products remain visible to administrators');
  assert.equal(stillThere.is_active, 0);
});
