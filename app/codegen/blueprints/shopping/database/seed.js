// Seed script: `npm run db:seed`
// Idempotent: safe to run against an existing database. Creates demo accounts,
// categories and a product catalogue so the storefront has real data to render.
import { migrate, query, queryOne, execute, databasePath } from './db.js';
import { hashPassword } from '../backend/lib/passwords.js';

const CATEGORIES = [
  { name: 'Apparel', slug: 'apparel', description: 'Considered everyday layers cut from natural fibres.' },
  { name: 'Home & Living', slug: 'home', description: 'Quiet objects that make a room feel finished.' },
  { name: 'Bags & Carry', slug: 'bags', description: 'Commuter-proof carry built for long days.' },
  { name: 'Kitchen', slug: 'kitchen', description: 'Brew, cook and serve with fewer, better tools.' },
  { name: 'Desk & Tech', slug: 'desk', description: 'Small hardware for focused work.' },
];

const PRODUCTS = [
  {
    slug: 'aurora-linen-shirt', name: 'Aurora Linen Shirt', category: 'apparel', price: 8900, stock: 42,
    badge: 'Bestseller', description: 'Relaxed-fit shirt in washed European linen with a soft, lived-in hand.',
    longDescription: 'The Aurora is cut from 100% washed European linen with a relaxed shoulder and a curved hem. It softens with every wash, works over a tee or on its own, and holds its shape through long days. Model is 183cm wearing size M.',
  },
  {
    slug: 'meridian-wool-overshirt', name: 'Meridian Wool Overshirt', category: 'apparel', price: 14200, stock: 18,
    badge: 'New season', description: 'Brushed wool overshirt with a hidden placket and twin chest pockets.',
    longDescription: 'A mid-weight layer in brushed Italian wool with a subtle herringbone. Two chest pockets, a hidden placket and a slight drop shoulder make it equally at home over a shirt or under a coat.',
  },
  {
    slug: 'halo-ceramic-mug', name: 'Halo Ceramic Mug', category: 'kitchen', price: 3200, stock: 120,
    badge: '', description: 'Speckled stoneware mug, glazed by hand in a warm chalk finish.',
    longDescription: 'Thrown in small batches from speckled stoneware and dipped in a chalk matte glaze. 320ml, dishwasher and microwave safe. Each piece carries small variations from the firing.',
  },
  {
    slug: 'solstice-table-lamp', name: 'Solstice Table Lamp', category: 'home', price: 18900, stock: 9,
    badge: 'Low stock', description: 'Solid oak lamp with a linen shade and a warm, dimmable glow.',
    longDescription: 'A solid oak base finished with hardwax oil, topped with a hand-stitched linen shade. Stepless dimming from a brass rotary switch, 2700K LED included. 42cm tall.',
  },
  {
    slug: 'atlas-weekender-tote', name: 'Atlas Weekender Tote', category: 'bags', price: 12600, stock: 24,
    badge: '', description: 'Waxed canvas tote with full-grain leather handles and an interior sleeve.',
    longDescription: '18oz waxed canvas with full-grain leather handles that darken as they age. Fits a 16-inch laptop, a change of clothes and a water bottle, with a zip pocket inside for the small things.',
  },
  {
    slug: 'vector-crossbody', name: 'Vector Crossbody', category: 'bags', price: 9800, stock: 31,
    badge: '', description: 'Compact recycled-nylon crossbody with magnetic quick access.',
    longDescription: 'Built from recycled ripstop nylon with a water-resistant coating. A magnetic top flap gives one-hand access, while the padded rear pocket keeps a phone or passport flat against your body.',
  },
  {
    slug: 'ember-pour-over-set', name: 'Ember Pour-Over Set', category: 'kitchen', price: 7400, stock: 27,
    badge: 'Staff pick', description: 'Borosilicate dripper, server and a reusable stainless filter.',
    longDescription: 'A complete two-cup setup: heat-resistant borosilicate dripper and 600ml server with a reusable etched stainless filter. No paper filters needed, no plastic in the brew path.',
  },
  {
    slug: 'nimbus-throw-blanket', name: 'Nimbus Throw Blanket', category: 'home', price: 8600, stock: 36,
    badge: '', description: 'Brushed cotton throw with a whipstitched edge, warm but breathable.',
    longDescription: 'Woven from long-staple cotton and brushed on both sides for a soft, weighty hand. 130 x 180cm with a hand-finished whipstitch edge. Machine washable at 30°C.',
  },
  {
    slug: 'drift-running-cap', name: 'Drift Running Cap', category: 'apparel', price: 3800, stock: 65,
    badge: '', description: 'Featherweight cap with laser-cut ventilation and a reflective tab.',
    longDescription: 'A 42g cap in recycled performance mesh with laser-cut side panels and a reflective rear tab. The soft brim packs flat into a pocket and the rear strap adjusts one-handed.',
  },
  {
    slug: 'quanta-desk-tray', name: 'Quanta Desk Tray', category: 'desk', price: 4200, stock: 58,
    badge: '', description: 'Machined aluminium tray with a felt base to corral desk clutter.',
    longDescription: 'Machined from a single billet of recycled aluminium with a bead-blasted finish and a wool felt base that protects your desk. Two wells for pens and small tools.',
  },
  {
    slug: 'orbit-headphones', name: 'Orbit Headphones', category: 'desk', price: 21900, stock: 14,
    badge: 'New', description: 'Closed-back wireless headphones with 40-hour battery and USB-C audio.',
    longDescription: 'Tuned for long listening sessions with memory-foam earpads and a machined aluminium yoke. 40 hours of playback, multipoint Bluetooth, and lossless USB-C audio for desk work.',
  },
  {
    slug: 'pilot-field-notebook', name: 'Pilot Field Notebook', category: 'desk', price: 1900, stock: 200,
    badge: '', description: 'Pocket notebook with 80gsm dot-grid paper and a lay-flat binding.',
    longDescription: 'A pocket-sized notebook that survives a bag. 48 sheets of 80gsm dot-grid paper, a lay-flat sewn binding, and a recycled board cover with a subtle deboss.',
  },
];

async function main() {
  await migrate();
  console.log(`Seeding ${databasePath()}`);

  for (const category of CATEGORIES) {
    const existing = await queryOne('SELECT id FROM categories WHERE slug = ?', category.slug);
    if (existing) continue;
    await execute(
      'INSERT INTO categories (name, slug, description) VALUES (?, ?, ?)',
      category.name, category.slug, category.description,
    );
  }

  const accounts = [
    { name: 'Nexora Admin', email: process.env.SEED_ADMIN_EMAIL || 'admin@shop.test', password: process.env.SEED_ADMIN_PASSWORD || 'Admin1234!', role: 'admin' },
    { name: 'Demo Customer', email: process.env.SEED_DEMO_EMAIL || 'demo@shop.test', password: process.env.SEED_DEMO_PASSWORD || 'Demo1234!', role: 'customer' },
  ];
  for (const account of accounts) {
    const existing = await queryOne('SELECT id FROM users WHERE email = ?', account.email.toLowerCase());
    if (existing) continue;
    await execute(
      'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
      account.name, account.email.toLowerCase(), hashPassword(account.password), account.role,
    );
  }

  for (const product of PRODUCTS) {
    const category = await queryOne('SELECT id FROM categories WHERE slug = ?', product.category);
    await execute(
      `INSERT INTO products (category_id, name, slug, description, long_description, price_cents, stock, image, badge)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(slug) DO UPDATE SET
         category_id = excluded.category_id,
         name = excluded.name,
         description = excluded.description,
         long_description = excluded.long_description,
         price_cents = excluded.price_cents,
         stock = excluded.stock,
         image = excluded.image,
         badge = excluded.badge`,
      category?.id ?? null, product.name, product.slug, product.description, product.longDescription,
      product.price, product.stock, `products/${product.slug}.svg`, product.badge,
    );
  }

  const counts = await Promise.all([
    queryOne('SELECT COUNT(*) AS total FROM products'),
    queryOne('SELECT COUNT(*) AS total FROM categories'),
    queryOne('SELECT COUNT(*) AS total FROM users'),
  ]);
  console.log(`Seed complete: ${counts[0].total} products, ${counts[1].total} categories, ${counts[2].total} users`);
  console.log('Demo customer: demo@shop.test / Demo1234!');
  console.log('Admin account: admin@shop.test / Admin1234!');
}

main().catch((error) => {
  console.error('Seed failed:', error.message);
  process.exitCode = 1;
});
