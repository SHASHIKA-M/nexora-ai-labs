import { query, queryOne, execute } from '../../database/db.js';
import { HttpError } from '../lib/validate.js';
import { MAX_LINE_QUANTITY, summarise } from '../lib/money.js';

const CART_SQL = `
  SELECT ci.id AS line_id, ci.quantity, ci.product_id,
         p.name, p.slug, p.image, p.price_cents, p.stock
    FROM cart_items ci
    JOIN products p ON p.id = ci.product_id
   WHERE ci.user_id = ?
   ORDER BY ci.id`;

export async function getCart(userId) {
  const lines = await query(CART_SQL, userId);
  const decorated = lines.map((line) => ({
    ...line,
    line_total_cents: line.price_cents * line.quantity,
    unavailable: line.stock === 0,
  }));
  return { items: decorated, ...summarise(decorated) };
}

export async function addItem(userId, productId, quantity = 1) {
  const product = await queryOne('SELECT id, stock, name FROM products WHERE id = ? AND is_active = 1', productId);
  if (!product) throw new HttpError(404, 'Product not found.');
  if (product.stock <= 0) throw new HttpError(409, `${product.name} is sold out.`);

  const existing = await queryOne('SELECT id, quantity FROM cart_items WHERE user_id = ? AND product_id = ?', userId, productId);
  const nextQuantity = Math.min((existing?.quantity ?? 0) + quantity, MAX_LINE_QUANTITY, product.stock);
  if (existing) {
    await execute('UPDATE cart_items SET quantity = ? WHERE id = ?', nextQuantity, existing.id);
  } else {
    await execute('INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)', userId, productId, nextQuantity);
  }
  return getCart(userId);
}

export async function updateItem(userId, productId, quantity) {
  const line = await queryOne(
    'SELECT ci.id, p.stock, p.name FROM cart_items ci JOIN products p ON p.id = ci.product_id WHERE ci.user_id = ? AND ci.product_id = ?',
    userId, productId,
  );
  if (!line) throw new HttpError(404, 'That product is not in your bag.');
  if (quantity > line.stock) throw new HttpError(409, `Only ${line.stock} of ${line.name} available.`);
  await execute('UPDATE cart_items SET quantity = ? WHERE id = ?', quantity, line.id);
  return getCart(userId);
}

export async function removeItem(userId, productId) {
  const result = await execute('DELETE FROM cart_items WHERE user_id = ? AND product_id = ?', userId, productId);
  if (!result.changes) throw new HttpError(404, 'That product is not in your bag.');
  return getCart(userId);
}

export async function clearCart(userId) {
  await execute('DELETE FROM cart_items WHERE user_id = ?', userId);
}
