import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient } from '../helpers/harness.js';
import { FIXTURES } from '../helpers/seedTestData.js';

test('product listing returns seeded products with pagination metadata', async () => {
  const { status, body } = await createClient().get('/api/products');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body.products));
  assert.ok(body.total >= 4);
  assert.ok(body.products.every((product) => typeof product.price_cents === 'number'));
});

test('category filter narrows results', async () => {
  const all = await createClient().get('/api/products');
  const filtered = await createClient().get('/api/products?category=apparel');
  assert.equal(filtered.status, 200);
  assert.ok(filtered.body.total <= all.body.total);
  assert.ok(filtered.body.products.every((product) => product.category_slug === 'apparel'));
});

test('search matches name and description', async () => {
  const { body } = await createClient().get('/api/products?search=lamp');
  assert.ok(body.products.some((product) => product.slug === FIXTURES.products.lamp));
});

test('sorting by price ascending orders results correctly', async () => {
  const { body } = await createClient().get('/api/products?sort=price-asc');
  const prices = body.products.map((product) => product.price_cents);
  assert.deepEqual(prices, [...prices].sort((a, b) => a - b));
});

test('product detail includes related products and stock flags', async () => {
  const { status, body } = await createClient().get(`/api/products/${FIXTURES.products.shirt}`);
  assert.equal(status, 200);
  assert.equal(body.product.slug, FIXTURES.products.shirt);
  assert.equal(body.product.in_stock, true);
  assert.ok(Array.isArray(body.related));
});

test('sold-out products are flagged and cannot be bought', async () => {
  const client = createClient();
  const detail = await client.get(`/api/products/${FIXTURES.products.soldOut}`);
  assert.equal(detail.body.product.in_stock, false);

  await client.register();
  const soldOutId = detail.body.product.id;
  const add = await client.post('/api/cart/items', { product_id: soldOutId, quantity: 1 });
  assert.equal(add.status, 409);
});

test('unknown product slug returns 404 JSON', async () => {
  const { status, body } = await createClient().get('/api/products/not-a-real-product');
  assert.equal(status, 404);
  assert.match(body.error, /not found/i);
});

test('categories endpoint reports product counts', async () => {
  const { status, body } = await createClient().get('/api/products/categories');
  assert.equal(status, 200);
  assert.ok(body.categories.length >= 1);
  assert.ok(body.categories.every((category) => typeof category.product_count === 'number'));
});
