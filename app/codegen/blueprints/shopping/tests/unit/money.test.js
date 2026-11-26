import test from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney, shippingFor, summarise, lineTotal, orderReference } from '../../backend/lib/money.js';

test('formatMoney renders integer cents as currency', () => {
  assert.equal(formatMoney(0), '$0.00');
  assert.equal(formatMoney(1999), '$19.99');
  assert.equal(formatMoney(123456), '$1,234.56');
});

test('shipping is free above the threshold and flat below it', () => {
  assert.equal(shippingFor(7500), 0);
  assert.equal(shippingFor(9000), 0);
  assert.equal(shippingFor(7499), 650);
  assert.equal(shippingFor(0), 0);
});

test('lineTotal multiplies price by quantity without floating point drift', () => {
  assert.equal(lineTotal(1999, 3), 5997);
  assert.equal(lineTotal(0.1 * 100, 3), 30);
});

test('summarise calculates subtotal, shipping, total and item count', () => {
  const summary = summarise([
    { price_cents: 2000, quantity: 2 },
    { price_cents: 1000, quantity: 1 },
  ]);
  assert.equal(summary.subtotal_cents, 5000);
  assert.equal(summary.shipping_cents, 650);
  assert.equal(summary.total_cents, 5650);
  assert.equal(summary.item_count, 3);
  assert.equal(summary.free_shipping_remaining_cents, 2500);
});

test('summarise removes shipping once the free threshold is met', () => {
  const summary = summarise([{ price_cents: 8000, quantity: 1 }]);
  assert.equal(summary.shipping_cents, 0);
  assert.equal(summary.total_cents, 8000);
  assert.equal(summary.free_shipping_remaining_cents, 0);
});

test('orderReference is unique and readable', () => {
  const references = new Set(Array.from({ length: 200 }, orderReference));
  assert.equal(references.size, 200);
  for (const reference of references) assert.match(reference, /^NX-\d{6}-[A-Z0-9]{5}$/);
});
