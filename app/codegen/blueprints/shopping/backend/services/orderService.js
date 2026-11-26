import { query, queryOne, execute, withTransaction } from '../../database/db.js';
import { HttpError, requireString, requireEnum } from '../lib/validate.js';
import { orderReference, summarise } from '../lib/money.js';

export const ORDER_STATUSES = ['pending', 'paid', 'packed', 'shipped', 'delivered', 'cancelled'];
const PAYMENT_METHODS = ['card_on_delivery', 'bank_transfer', 'demo_card'];

function requireAddress(payload) {
  return {
    customer_name: requireString(payload.customer_name, 'Full name', { max: 120 }),
    customer_email: requireString(payload.customer_email, 'Email', { max: 254 }),
    shipping_address: requireString(payload.shipping_address, 'Address', { min: 5, max: 200 }),
    shipping_city: requireString(payload.shipping_city, 'City', { max: 80 }),
    shipping_postal: requireString(payload.shipping_postal, 'Postal code', { max: 20 }),
    shipping_country: requireString(payload.shipping_country, 'Country', { max: 80 }),
    notes: typeof payload.notes === 'string' ? payload.notes.slice(0, 500) : '',
    payment_method: requireEnum(payload.payment_method || 'demo_card', 'Payment method', PAYMENT_METHODS),
  };
}

export async function placeOrder(userId, payload) {
  const address = requireAddress(payload);
  const lines = await query(
    `SELECT ci.product_id, ci.quantity, p.name, p.price_cents, p.stock
       FROM cart_items ci JOIN products p ON p.id = ci.product_id
      WHERE ci.user_id = ? ORDER BY ci.id`,
    userId,
  );
  if (!lines.length) throw new HttpError(400, 'Your bag is empty.');

  for (const line of lines) {
    if (line.quantity > line.stock) {
      throw new HttpError(409, `Only ${line.stock} of ${line.name} left. Please update your bag.`);
    }
  }

  const totals = summarise(lines);
  const reference = orderReference();

  const orderId = await withTransaction(async () => {
    const created = await execute(
      `INSERT INTO orders (user_id, reference, status, payment_method, customer_name, customer_email,
                           shipping_address, shipping_city, shipping_postal, shipping_country, notes,
                           subtotal_cents, shipping_cents, total_cents)
       VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      userId, reference, address.payment_method, address.customer_name, address.customer_email.toLowerCase(),
      address.shipping_address, address.shipping_city, address.shipping_postal, address.shipping_country,
      address.notes, totals.subtotal_cents, totals.shipping_cents, totals.total_cents,
    );
    const id = Number(created.lastInsertRowid);
    for (const line of lines) {
      await execute(
        `INSERT INTO order_items (order_id, product_id, product_name, unit_price_cents, quantity)
         VALUES (?, ?, ?, ?, ?)`,
        id, line.product_id, line.name, line.price_cents, line.quantity,
      );
      await execute('UPDATE products SET stock = stock - ? WHERE id = ?', line.quantity, line.product_id);
    }
    await execute('INSERT INTO order_events (order_id, status, note) VALUES (?, ?, ?)', id, 'pending', 'Order placed by customer.');
    await execute('DELETE FROM cart_items WHERE user_id = ?', userId);
    return id;
  });

  return getOrder(orderId, { userId });
}

export async function listOrdersForUser(userId) {
  const orders = await query(
    `SELECT id, reference, status, total_cents, item_count FROM (
       SELECT o.id, o.reference, o.status, o.total_cents, o.created_at,
              (SELECT SUM(quantity) FROM order_items oi WHERE oi.order_id = o.id) AS item_count
         FROM orders o WHERE o.user_id = ?
     ) ORDER BY id DESC`,
    userId,
  );
  return orders.map((order) => ({ ...order, item_count: order.item_count ?? 0 }));
}

export async function getOrder(orderId, { userId = null, isAdmin = false } = {}) {
  const order = await queryOne('SELECT * FROM orders WHERE id = ?', orderId);
  if (!order) throw new HttpError(404, 'Order not found.');
  if (!isAdmin && order.user_id !== userId) throw new HttpError(403, 'You cannot view this order.');
  const [items, events] = await Promise.all([
    query('SELECT * FROM order_items WHERE order_id = ? ORDER BY id', orderId),
    query('SELECT * FROM order_events WHERE order_id = ? ORDER BY id', orderId),
  ]);
  return { order, items, events };
}

export async function cancelOrder(userId, orderId) {
  const { order } = await getOrder(orderId, { userId });
  if (!['pending', 'paid'].includes(order.status)) {
    throw new HttpError(409, `Orders that are ${order.status} can no longer be cancelled.`);
  }
  await withTransaction(async () => {
    const items = await query('SELECT product_id, quantity FROM order_items WHERE order_id = ?', orderId);
    for (const item of items) {
      if (item.product_id) {
        await execute('UPDATE products SET stock = stock + ? WHERE id = ?', item.quantity, item.product_id);
      }
    }
    await execute("UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?", new Date().toISOString(), orderId);
    await execute('INSERT INTO order_events (order_id, status, note) VALUES (?, ?, ?)', orderId, 'cancelled', 'Cancelled by customer.');
  });
  return getOrder(orderId, { userId });
}

export async function updateStatus(orderId, status, note = '') {
  requireEnum(status, 'Status', ORDER_STATUSES);
  const order = await queryOne('SELECT id, status FROM orders WHERE id = ?', orderId);
  if (!order) throw new HttpError(404, 'Order not found.');
  if (order.status === 'cancelled') throw new HttpError(409, 'A cancelled order cannot change status.');
  if (order.status === status) return getOrder(orderId, { isAdmin: true });
  await withTransaction(async () => {
    await execute('UPDATE orders SET status = ?, updated_at = ? WHERE id = ?', status, new Date().toISOString(), orderId);
    await execute('INSERT INTO order_events (order_id, status, note) VALUES (?, ?, ?)', orderId, status, note.slice(0, 300));
  });
  return getOrder(orderId, { isAdmin: true });
}

export async function adminStats() {
  const [revenue, orders, customers, lowStock, recent] = await Promise.all([
    queryOne("SELECT COALESCE(SUM(total_cents), 0) AS total FROM orders WHERE status != 'cancelled'"),
    queryOne('SELECT COUNT(*) AS total FROM orders'),
    queryOne("SELECT COUNT(*) AS total FROM users WHERE role = 'customer'"),
    query('SELECT id, name, stock, slug FROM products WHERE stock <= 10 ORDER BY stock ASC LIMIT 5'),
    query(`SELECT id, reference, status, total_cents, customer_name, created_at FROM orders ORDER BY id DESC LIMIT 6`),
  ]);
  const byStatus = await query('SELECT status, COUNT(*) AS total FROM orders GROUP BY status');
  return {
    revenue_cents: revenue?.total ?? 0,
    order_count: orders?.total ?? 0,
    customer_count: customers?.total ?? 0,
    low_stock: lowStock,
    recent_orders: recent,
    orders_by_status: byStatus,
  };
}
