import test from 'node:test';
import assert from 'node:assert/strict';
import { hashPassword, verifyPassword } from '../../backend/lib/passwords.js';

test('hashPassword produces a salted scrypt hash, never the plaintext', () => {
  const hash = hashPassword('Secret123');
  assert.match(hash, /^scrypt\$[0-9a-f]{32}\$[0-9a-f]{128}$/);
  assert.ok(!hash.includes('Secret123'));
});

test('the same password hashes differently each time (unique salt)', () => {
  assert.notEqual(hashPassword('Secret123'), hashPassword('Secret123'));
});

test('verifyPassword accepts the correct password and rejects others', () => {
  const hash = hashPassword('Secret123');
  assert.equal(verifyPassword('Secret123', hash), true);
  assert.equal(verifyPassword('secret123', hash), false);
  assert.equal(verifyPassword('', hash), false);
});

test('verifyPassword fails safely on malformed stored hashes', () => {
  assert.equal(verifyPassword('Secret123', null), false);
  assert.equal(verifyPassword('Secret123', 'plaintext'), false);
  assert.equal(verifyPassword('Secret123', 'bcrypt$aa$bb'), false);
  assert.equal(verifyPassword('Secret123', 'scrypt$zz$zz'), false);
});
