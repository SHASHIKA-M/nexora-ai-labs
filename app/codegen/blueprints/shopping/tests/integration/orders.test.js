import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient } from '../helpers/harness.js';
import { FIXTURES } from '../helpers/seedTestData.js';

const ADDRESS = {
  customer_name: 'Test Customer',
  customer_email: 'buyer@example.com',
  shipping_address: '12 Harbour Road, Apt 4B',
  shipping_city: 'Singapore',
  shipping_postal: '049213',
  shipping_country: 'Singapore',
  payment_method: 'demo_card',
  notes: 'Leave with concierge',
};

async function customerWithItem(quantity = 2) {
  const client = createClient();
  await client.register({ email: `buyer${Math.random().toString(36).slice(2, 8)}@example.com` });
  const { body } = await client.get('/api/products/test-shirt');
  await client.post('/api/cart/items', { product_id: body.product.id, quantity });
  return client;
}

test('checkout creates a real order, clears the cart and decrements stock', async () => {
  const client = await customerWithItem(2);
  const before = (await client.get('/api/products/test-shirt')).body.product.stock;

  const placed = await client.post('/api/orders', ADDRESS);
  assert.equal(placed.status, 201);
  assert.match(placed.body.order.reference, /^NX-/);
  assert.equal(placed.body.order.status, 'pending');
  assert.equal(placed.body.items.length, 1);
  assert.equal(placed.body.items[0].quantity, 2);
  assert.equal(placed.body.order.subtotal_cents, 10000);
  assert.ok(placed.body.events.some((event) => event.status === 'pending'));

  const after = (await client.get('/api/products/test-shirt')).body.product.stock;
  assert.equal(after, before - 2, 'stock is decremented inside the checkout transaction');

  const cart = await client.get('/api/cart');
  assert.equal(cart.body.item_count, 0);
});

test('checkout rejects an empty cart', async () => {
  const client = createClient();
  await client.register();
  const result = await client.post('/api/orders', ADDRESS);
  assert.equal(result.status, 400);
});

test('checkout validates the shipping payload field by field', async () => {
  const client = await customerWithItem(1);
  const missingCity = await client.post('/api/orders', { ...ADDRESS, shipping_city: '' });
  assert.equal(missingCity.status, 422);
  assert.match(missingCity.body.error, /City/);

  const shortAddress = await client.post('/api/orders', { ...ADDRESS, shipping_address: 'ab' });
  assert.equal(shortAddress.status, 422);

  const badPayment = await client.post('/api/orders', { ...ADDRESS, payment_method: 'bitcoin' });
  assert.equal(badPayment.status, 422);
});

test('customers can list and read their own orders', async () => {
  const client = await customerWithItem(1);
  const placed = await client.post('/api/orders', ADDRESS);
  const list = await client.get('/api/orders');
  assert.equal(list.status, 200);
  assert.ok(list.body.orders.some((order) => order.id === placed.body.order.id));

  const detail = await client.get(`/api/orders/${placed.body.order.id}`);
  assert.equal(detail.status, 200);
  assert.equal(detail.body.order.reference, placed.body.order.reference);
});

test('one customer cannot read another customer\'s order', async () => {
  const owner = await customerWithItem(1);
  const placed = await owner.post('/api/orders', ADDRESS);

  const intruder = createClient();
  await intruder.register();
  const attempt = await intruder.get(`/api/orders/${placed.body.order.id}`);
  assert.equal(attempt.status, 403);
});

test('cancelling an order restores stock and records an event', async () => {
  const client = await customerWithItem(2);
  const before = (await client.get('/api/products/test-shirt')).body.product.stock;
  const placed = await client.post('/api/orders', ADDRESS);
  const cancelled = await client.post(`/api/orders/${placed.body.order.id}/cancel`, {});

  assert.equal(cancelled.status, 200);
  assert.equal(cancelled.body.order.status, 'cancelled');
  const after = (await client.get('/api/products/test-shirt')).body.product.stock;
  assert.equal(after, before);
});

test('admin can advance order status and customers cannot', async () => {
  const customer = await customerWithItem(1);
  const placed = await customer.post('/api/orders', ADDRESS);
  const orderId = placed.body.order.id;

  const denied = await customer.post(`/api/admin/orders/${orderId}/status`, { status: 'shipped' });
  assert.equal(denied.status, 403);

  const admin = createClient();
  await admin.loginAs(FIXTURES.admin.email, FIXTURES.admin.password);
  const shipped = await admin.post(`/api/admin/orders/${orderId}/status`, { status: 'shipped', note: 'Handed to courier' });
  assert.equal(shipped.status, 200);
  assert.equal(shipped.body.order.status, 'shipped');
  assert.ok(shipped.body.events.some((event) => event.status === 'shipped'));

  const invalid = await admin.post(`/api/admin/orders/${orderId}/status`, { status: 'teleported' });
  assert.equal(invalid.status, 422);
});

test('a shipped order can no longer be cancelled by the customer', async () => {
  const customer = await customerWithItem(1);
  const placed = await customer.post('/api/orders', ADDRESS);
  const admin = createClient();
  await admin.loginAs(FIXTURES.admin.email, FIXTURES.admin.password);
  await admin.post(`/api/admin/orders/${placed.body.order.id}/status`, { status: 'packed' });

  const attempt = await customer.post(`/api/orders/${placed.body.order.id}/cancel`, {});
  assert.equal(attempt.status, 409);
});

test('admin stats aggregate real order and customer data', async () => {
  const admin = createClient();
  await admin.loginAs(FIXTURES.admin.email, FIXTURES.admin.password);
  const { status, body } = await admin.get('/api/admin/stats');
  assert.equal(status, 200);
  assert.ok(body.order_count >= 1);
  assert.ok(body.revenue_cents > 0);
  assert.ok(Array.isArray(body.recent_orders));
  assert.ok(Array.isArray(body.orders_by_status));
});
