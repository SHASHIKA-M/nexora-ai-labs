// Currency helpers. Money is always handled as integer cents.
export const FREE_SHIPPING_THRESHOLD_CENTS = Number(process.env.FREE_SHIPPING_THRESHOLD_CENTS || 7500);
export const SHIPPING_FLAT_CENTS = Number(process.env.SHIPPING_FLAT_CENTS || 650);
export const MAX_LINE_QUANTITY = 99;

export function formatMoney(cents) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(cents || 0) / 100);
}

export function shippingFor(subtotalCents) {
  if (subtotalCents <= 0) return 0;
  return subtotalCents >= FREE_SHIPPING_THRESHOLD_CENTS ? 0 : SHIPPING_FLAT_CENTS;
}

export function orderReference() {
  const stamp = new Date().toISOString().slice(2, 10).replace(/-/g, '');
  const random = Math.random().toString(36).slice(2, 7).toUpperCase();
  return `NX-${stamp}-${random}`;
}

export function lineTotal(priceCents, quantity) {
  return Number(priceCents) * Number(quantity);
}

export function summarise(lines) {
  const subtotal = lines.reduce((total, line) => total + lineTotal(line.price_cents, line.quantity), 0);
  const shipping = shippingFor(subtotal);
  return {
    subtotal_cents: subtotal,
    shipping_cents: shipping,
    total_cents: subtotal + shipping,
    item_count: lines.reduce((total, line) => total + Number(line.quantity), 0),
    free_shipping_remaining_cents: Math.max(0, FREE_SHIPPING_THRESHOLD_CENTS - subtotal),
  };
}
