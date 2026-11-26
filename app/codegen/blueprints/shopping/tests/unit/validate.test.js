import test from 'node:test';
import assert from 'node:assert/strict';
import {
  requireString, requireEmail, requirePassword, requireInt, requireEnum, escapeHtml, slugify, HttpError,
} from '../../backend/lib/validate.js';

test('requireString trims, enforces length, and throws HttpError(422)', () => {
  assert.equal(requireString('  hello  ', 'Name'), 'hello');
  assert.throws(() => requireString('', 'Name'), HttpError);
  assert.throws(() => requireString('a', 'Name', { min: 3 }), /at least 3/);
  assert.throws(() => requireString('abcdef', 'Name', { max: 3 }), /at most 3/);
  assert.throws(() => requireString(42, 'Name'), HttpError);
});

test('requireEmail normalises case and rejects malformed input', () => {
  assert.equal(requireEmail('Person@Example.COM'), 'person@example.com');
  for (const bad of ['nope', 'a@b', 'a b@c.com', '@x.com', '']) {
    assert.throws(() => requireEmail(bad), HttpError, `expected ${bad} to fail`);
  }
});

test('requirePassword enforces minimum strength', () => {
  assert.equal(requirePassword('Password123'), 'Password123');
  assert.throws(() => requirePassword('short1'), /at least 8/);
  assert.throws(() => requirePassword('onlyletters'), /letters and numbers/);
  assert.throws(() => requirePassword('12345678'), /letters and numbers/);
});

test('requireInt rejects floats, negatives and out-of-range values', () => {
  assert.equal(requireInt('5', 'Quantity'), 5);
  assert.throws(() => requireInt(1.5, 'Quantity'), /whole number/);
  assert.throws(() => requireInt(0, 'Quantity'), /between/);
  assert.throws(() => requireInt(100, 'Quantity'), /between/);
});

test('requireEnum only accepts known values', () => {
  assert.equal(requireEnum('paid', 'Status', ['paid', 'shipped']), 'paid');
  assert.throws(() => requireEnum('refunded', 'Status', ['paid']), /must be one of/);
});

test('escapeHtml neutralises markup for safe interpolation', () => {
  assert.equal(escapeHtml('<script>alert("x")</script>'),
    '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
  assert.equal(escapeHtml("it's & fine"), 'it&#39;s &amp; fine');
});

test('slugify produces URL-safe slugs', () => {
  assert.equal(slugify('Aurora Linen Shirt!'), 'aurora-linen-shirt');
  assert.equal(slugify('  --Weird   Name--  '), 'weird-name');
});
