import { query, queryOne } from '../../database/db.js';
import { HttpError } from '../lib/validate.js';

const SORTS = {
  featured: 'p.is_active DESC, p.id ASC',
  newest: 'p.created_at DESC',
  'price-asc': 'p.price_cents ASC',
  'price-desc': 'p.price_cents DESC',
  name: 'p.name ASC',
};

const SELECT_PRODUCT = `
  SELECT p.id, p.category_id, p.name, p.slug, p.description, p.long_description, p.price_cents, p.stock,
         p.image, p.badge, p.is_active, p.created_at,
         c.name AS category_name, c.slug AS category_slug
    FROM products p
    LEFT JOIN categories c ON c.id = p.category_id`;

export async function listCategories() {
  return query(`
    SELECT c.id, c.name, c.slug, c.description, COUNT(p.id) AS product_count
      FROM categories c
      LEFT JOIN products p ON p.category_id = c.id AND p.is_active = 1
     GROUP BY c.id
     ORDER BY c.name`);
}

export async function listProducts({ category, search, sort = 'featured', limit = 24, offset = 0, includeInactive = false } = {}) {
  const clauses = [];
  const params = [];
  if (!includeInactive) clauses.push('p.is_active = 1');
  if (category) {
    clauses.push('c.slug = ?');
    params.push(category);
  }
  if (search) {
    clauses.push('(p.name LIKE ? OR p.description LIKE ?)');
    params.push(`%${search}%`, `%${search}%`);
  }
  const where = clauses.length ? ` WHERE ${clauses.join(' AND ')}` : '';
  const order = SORTS[sort] || SORTS.featured;
  const safeLimit = Math.min(Math.max(Number(limit) || 24, 1), 60);
  const safeOffset = Math.max(Number(offset) || 0, 0);
  const rows = await query(`${SELECT_PRODUCT}${where} ORDER BY ${order} LIMIT ? OFFSET ?`, ...params, safeLimit, safeOffset);
  const countRow = await queryOne(
    `SELECT COUNT(*) AS total FROM products p LEFT JOIN categories c ON c.id = p.category_id${where}`,
    ...params,
  );
  return { products: rows.map(decorate), total: countRow?.total ?? 0, limit: safeLimit, offset: safeOffset };
}

export function decorate(product) {
  return { ...product, in_stock: product.stock > 0, low_stock: product.stock > 0 && product.stock <= 10 };
}

export async function getProductBySlug(slug) {
  const product = await queryOne(`${SELECT_PRODUCT} WHERE p.slug = ? AND p.is_active = 1`, slug);
  if (!product) throw new HttpError(404, 'Product not found.');
  const related = await query(
    `${SELECT_PRODUCT} WHERE p.category_id = ? AND p.id != ? AND p.is_active = 1 ORDER BY p.id LIMIT 4`,
    product.category_id ?? -1,
    product.id,
  ).catch(() => []);
  return { product: decorate(product), related: related.map(decorate) };
}
