import { Router } from 'express';
import { requireAdmin } from '../middleware/auth.js';
import { adminStats, updateStatus, getOrder, listOrdersForUser } from '../services/orderService.js';
import { listCustomers } from '../services/userService.js';
import { listProducts } from '../services/catalogService.js';
import { query, queryOne, execute } from '../../database/db.js';
import { HttpError, requireInt, requireString, requireEnum } from '../lib/validate.js';
import { slugify } from '../lib/validate.js';
import { ORDER_STATUSES } from '../services/orderService.js';

const router = Router();
router.use(requireAdmin);

router.get('/stats', async (_req, res, next) => {
  try {
    res.json(await adminStats());
  } catch (error) {
    next(error);
  }
});

router.get('/orders', async (req, res, next) => {
  try {
    const status = req.query.status;
    const params = [];
    let where = '';
    if (status && ORDER_STATUSES.includes(status)) {
      where = 'WHERE o.status = ?';
      params.push(status);
    }
    const orders = await query(
      `SELECT o.id, o.reference, o.status, o.total_cents, o.customer_name, o.customer_email, o.created_at,
              (SELECT SUM(quantity) FROM order_items oi WHERE oi.order_id = o.id) AS item_count
         FROM orders o ${where} ORDER BY o.id DESC LIMIT 100`,
      ...params,
    );
    res.json({ orders });
  } catch (error) {
    next(error);
  }
});

router.get('/orders/:id', async (req, res, next) => {
  try {
    res.json(await getOrder(requireInt(req.params.id, 'Order', { min: 1, max: 1_000_000 }), { isAdmin: true }));
  } catch (error) {
    next(error);
  }
});

router.post('/orders/:id/status', async (req, res, next) => {
  try {
    const id = requireInt(req.params.id, 'Order', { min: 1, max: 1_000_000 });
    const status = requireEnum(req.body?.status, 'Status', ORDER_STATUSES);
    const note = typeof req.body?.note === 'string' ? requireString(req.body.note, 'Note', { max: 300 }) : 'Updated by admin.';
    res.json(await updateStatus(id, status, note));
  } catch (error) {
    next(error);
  }
});

router.get('/customers', async (_req, res, next) => {
  try {
    res.json({ customers: await listCustomers() });
  } catch (error) {
    next(error);
  }
});

router.get('/products', async (req, res, next) => {
  try {
    res.json(await listProducts({ limit: 60, includeInactive: true }));
  } catch (error) {
    next(error);
  }
});

router.patch('/products/:id', async (req, res, next) => {
  try {
    const id = requireInt(req.params.id, 'Product', { min: 1, max: 1_000_000 });
    const product = await queryOne('SELECT * FROM products WHERE id = ?', id);
    if (!product) throw new HttpError(404, 'Product not found.');
    const priceCents = req.body?.price_cents === undefined
      ? product.price_cents
      : requireInt(req.body.price_cents, 'Price (cents)', { min: 0, max: 100_000_000 });
    const stock = req.body?.stock === undefined
      ? product.stock
      : requireInt(req.body.stock, 'Stock', { min: 0, max: 100000 });
    const name = req.body?.name === undefined ? product.name : requireString(req.body.name, 'Name', { max: 160 });
    const isActive = req.body?.is_active === undefined ? product.is_active : (req.body.is_active ? 1 : 0);
    await execute(
      'UPDATE products SET name = ?, price_cents = ?, stock = ?, is_active = ?, slug = ? WHERE id = ?',
      name, priceCents, stock, isActive, slugify(name) || product.slug, id,
    );
    res.json({ product: await queryOne('SELECT * FROM products WHERE id = ?', id) });
  } catch (error) {
    next(error);
  }
});

router.post('/products', async (req, res, next) => {
  try {
    const name = requireString(req.body?.name, 'Name', { max: 160 });
    const priceCents = requireInt(req.body?.price_cents, 'Price (cents)', { min: 1, max: 100_000_000 });
    const stock = requireInt(req.body?.stock ?? 0, 'Stock', { min: 0, max: 100000 });
    const categoryId = req.body?.category_id ? requireInt(req.body.category_id, 'Category', { min: 1, max: 1_000_000 }) : null;
    const description = typeof req.body?.description === 'string' ? req.body.description.slice(0, 500) : '';
    const slug = slugify(name);
    const existing = await queryOne('SELECT id FROM products WHERE slug = ?', slug);
    if (existing) throw new HttpError(409, 'A product with a similar name already exists.');
    const created = await execute(
      `INSERT INTO products (category_id, name, slug, description, long_description, price_cents, stock, image, badge)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')`,
      categoryId, name, slug, description, description, priceCents, stock, 'products/aurora-linen-shirt.svg',
    );
    res.status(201).json({ product: await queryOne('SELECT * FROM products WHERE id = ?', Number(created.lastInsertRowid)) });
  } catch (error) {
    next(error);
  }
});

export default router;
