// Deterministic fixtures for the test database. Uses the same seeding code path
// as production so tests exercise real inserts, hashing and constraints.
import { migrate, execute, queryOne } from '../../database/db.js';
import { hashPassword } from '../../backend/lib/passwords.js';

export async function seedTestData() {
  await migrate();

  const existing = await queryOne('SELECT COUNT(*) AS total FROM products');
  if ((existing?.total ?? 0) > 0) return;

  const category = await execute(
    'INSERT INTO categories (name, slug, description) VALUES (?, ?, ?)',
    'Apparel', 'apparel', 'Test category',
  );

  const products = [
    { name: 'Test Shirt', slug: 'test-shirt', price: 5000, stock: 10, badge: 'Test' },
    { name: 'Test Lamp', slug: 'test-lamp', price: 12000, stock: 3, badge: '' },
    { name: 'Sold Out Mug', slug: 'sold-out-mug', price: 2500, stock: 0, badge: '' },
    { name: 'Cheap Notebook', slug: 'cheap-notebook', price: 1000, stock: 100, badge: '' },
  ];
  for (const product of products) {
    await execute(
      `INSERT INTO products (category_id, name, slug, description, long_description, price_cents, stock, image, badge)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      Number(category.lastInsertRowid), product.name, product.slug, `${product.name} description`,
      `${product.name} long description`, product.price, product.stock, '/products/aurora-linen-shirt.svg', product.badge,
    );
  }

  await execute(
    'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
    'Admin Tester', 'admin@test.local', hashPassword('AdminPass123'), 'admin',
  );
  await execute(
    'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
    'Demo Tester', 'demo@test.local', hashPassword('DemoPass123'), 'customer',
  );
  return true;
}

export const FIXTURES = {
  admin: { email: 'admin@test.local', password: 'AdminPass123' },
  customer: { email: 'demo@test.local', password: 'DemoPass123' },
  products: {
    shirt: 'test-shirt',
    lamp: 'test-lamp',
    soldOut: 'sold-out-mug',
    notebook: 'cheap-notebook',
  },
};
