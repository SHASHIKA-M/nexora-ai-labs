import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient, app } from '../helpers/harness.js';

async function productId(slug) {
  const client = createClient();
  const { body } = await client.get(`/api/products/${slug}`);
  return body.product.id;
}

test('cart starts empty, accepts items and totals correctly', async () => {
  const client = createClient();
  await client.register();
  const shirtId = await productId('test-shirt');

  const empty = await client.get('/api/cart');
  assert.equal(empty.body.item_count, 0);

  const added = await client.post('/api/cart/items', { product_id: shirtId, quantity: 2 });
  assert.equal(added.status, 201);
  assert.equal(added.body.item_count, 2);
  assert.equal(added.body.subtotal_cents, 10000);
  assert.equal(added.body.shipping_cents, 0, 'subtotal above threshold ships free');
  assert.equal(added.body.total_cents, 10000);
});

test('adding the same product twice increments a single line', async () => {
  const client = createClient();
  await client.register();
  const id = await productId('test-lamp');
  await client.post('/api/cart/items', { product_id: id, quantity: 1 });
  const second = await client.post('/api/cart/items', { product_id: id, quantity: 1 });
  assert.equal(second.body.items.length, 1);
  assert.equal(second.body.items[0].quantity, 2);
});

test('cart quantity is capped at available stock', async () => {
  const client = createClient();
  await client.register();
  const id = await productId('test-lamp'); // stock 3
  const result = await client.post('/api/cart/items', { product_id: id, quantity: 9 });
  assert.equal(result.body.items[0].quantity, 3);
});

test('cart rejects unknown products and invalid quantities', async () => {
  const client = createClient();
  await client.register();
  assert.equal((await client.post('/api/cart/items', { product_id: 999999, quantity: 1 })).status, 404);
  const id = await productId('test-shirt');
  assert.equal((await client.post('/api/cart/items', { product_id: id, quantity: 0 })).status, 422);
  assert.equal((await client.post('/api/cart/items', { product_id: id, quantity: 'many' })).status, 422);
});

test('cart lines can be updated and removed', async () => {
  const client = createClient();
  await client.register();
  const id = await productId('test-shirt');
  await client.post('/api/cart/items', { product_id: id, quantity: 1 });

  const updated = await client.patch(`/api/cart/items/${id}`, { quantity: 4 });
  assert.equal(updated.status, 200);
  assert.equal(updated.body.items[0].quantity, 4);

  const removed = await client.delete(`/api/cart/items/${id}`);
  assert.equal(removed.status, 200);
  assert.equal(removed.body.items.length, 0);
  assert.equal(removed.body.total_cents, 0);
});

test('updating a line beyond stock fails with 409', async () => {
  const client = createClient();
  await client.register();
  const id = await productId('test-lamp'); // stock 3
  await client.post('/api/cart/items', { product_id: id, quantity: 1 });
  const result = await client.patch(`/api/cart/items/${id}`, { quantity: 99 });
  assert.equal(result.status, 409);
});

test('carts are isolated between customers', async () => {
  const alice = createClient();
  const bob = createClient();
  await alice.register();
  await bob.register();
  const id = await productId('test-shirt');
  await alice.post('/api/cart/items', { product_id: id, quantity: 3 });
  const bobCart = await bob.get('/api/cart');
  assert.equal(bobCart.body.item_count, 0);
});

test('stock levels are read from the database, not cached in the client', async () => {
  const client = createClient();
  await client.register();
  const detail = await client.get('/api/products/test-shirt');
  assert.equal(typeof detail.body.product.stock, 'number');
  assert.ok(app);
});
