// Shared storefront components: product cards, skeletons, error states.
import { esc, money, el } from '../lib/dom.js';

export function productCard(product) {
  const badge = product.badge ? `<span class="badge">${esc(product.badge)}</span>` : '';
  const stockLabel = product.stock <= 0
    ? '<span class="stock out">Sold out</span>'
    : product.low_stock
      ? '<span class="stock low">Low stock</span>'
      : '<span class="stock">In stock</span>';
  return `
    <article class="product-card">
      <a class="product-media" href="#/product/${encodeURIComponent(product.slug)}" aria-label="${esc(product.name)}">
        <img src="${esc(product.image)}" alt="${esc(product.name)}" width="400" height="400" loading="lazy">
        ${badge}${stockLabel}
      </a>
      <div class="product-body">
        <p class="product-kicker">${esc(product.category_name || 'Collection')}</p>
        <h3><a href="#/product/${encodeURIComponent(product.slug)}">${esc(product.name)}</a></h3>
        <p class="product-desc">${esc(product.description)}</p>
        <div class="product-foot">
          <span class="price">${money(product.price_cents)}</span>
          <button class="btn small" data-add-to-cart="${product.id}" ${product.stock > 0 ? '' : 'disabled'}>
            ${product.stock > 0 ? 'Add to bag' : 'Sold out'}
          </button>
        </div>
      </div>
    </article>`;
}

export function productGrid(products) {
  if (!products.length) {
    return `<div class="empty-state"><h2>No products found</h2><p>Try a different category or clear your search.</p></div>`;
  }
  return `<div class="product-grid">${products.map(productCard).join('')}</div>`;
}

export function skeletonGrid(count = 8) {
  return `<div class="product-grid">${Array.from({ length: count }, () => `
    <div class="product-card">
      <div class="product-media" style="background:linear-gradient(100deg,#161a22,#1d222b,#161a22)"></div>
      <div class="product-body">
        <div style="height:10px;width:40%;background:#1d222b;border-radius:4px"></div>
        <div style="height:16px;width:75%;background:#1d222b;border-radius:4px"></div>
        <div style="height:10px;width:90%;background:#1d222b;border-radius:4px"></div>
      </div>
    </div>`).join('')}</div>`;
}

export function errorState(message, retryId = 'retryBtn') {
  return `<div class="empty-state">
    <h2>Something went wrong</h2>
    <p>${esc(message)}</p>
    <button class="btn secondary" id="${retryId}">Try again</button>
  </div>`;
}

export function statusPill(status) {
  return `<span class="status-pill" data-status="${esc(status)}">${esc(status)}</span>`;
}

export function summaryCard(cart, { actionLabel = 'Proceed to checkout', actionHref = '#/checkout', showShippingNote = true } = {}) {
  const progress = Math.min(100, Math.round((cart.subtotal_cents / 7500) * 100));
  return `
    <aside class="card summary" aria-label="Order summary">
      <h3>Order summary</h3>
      ${showShippingNote ? `
      <div class="ship-progress">
        <p class="small muted" style="margin:0">${cart.free_shipping_remaining_cents > 0
          ? `Add ${money(cart.free_shipping_remaining_cents)} more for free shipping`
          : 'Free shipping unlocked'}</p>
        <div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>
      </div>` : ''}
      <div class="summary-row"><span class="muted">Subtotal (${cart.item_count} item${cart.item_count === 1 ? '' : 's'})</span><span>${money(cart.subtotal_cents)}</span></div>
      <div class="summary-row"><span class="muted">Shipping</span><span>${cart.shipping_cents === 0 ? 'Free' : money(cart.shipping_cents)}</span></div>
      <div class="summary-row total"><span>Total</span><span>${money(cart.total_cents)}</span></div>
      ${actionLabel ? `<a class="btn block" href="${actionHref}" style="margin-top:16px">${esc(actionLabel)}</a>` : ''}
    </aside>`;
}

export function mountAddToCart(root, onAdd) {
  root.addEventListener('click', (event) => {
    const button = event.target.closest('[data-add-to-cart]');
    if (!button) return;
    event.preventDefault();
    onAdd(Number(button.dataset.addToCart), button);
  });
}

export function setButtonBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.disabled = true;
    button.textContent = label || 'Working…';
  } else {
    button.disabled = false;
    if (button.dataset.label) button.textContent = button.dataset.label;
  }
}

export function hero() {
  return `
    <section class="hero">
      <div>
        <p class="eyebrow">Autumn collection · 2026</p>
        <h1>Everyday objects,<br><em>considered.</em></h1>
        <p class="lead">Twelve pieces made in small batches, designed to be used every day and kept for years. No seasonal churn, no filler.</p>
        <div class="hero-actions">
          <a class="btn" href="#/shop">Shop the collection</a>
          <a class="btn secondary" href="#/shop?category=home">Home &amp; living</a>
        </div>
        <div class="hero-figures">
          <div><strong>12</strong><span>Products</span></div>
          <div><strong>30-day</strong><span>Returns</span></div>
          <div><strong>2–4 day</strong><span>Delivery</span></div>
        </div>
      </div>
      <div class="hero-visual">
        <img src="/hero.svg" alt="A styled arrangement of Aurora & Co. products" width="760" height="420">
        <div class="hero-tag">
          <div><strong>Solstice Table Lamp</strong><span>Solid oak · linen shade</span></div>
          <a class="btn small secondary" href="#/product/solstice-table-lamp">View</a>
        </div>
      </div>
    </section>`;
}

export function sectionHead(title, subtitle, action) {
  return `<div class="section-head">
    <div><h2>${esc(title)}</h2>${subtitle ? `<p class="muted" style="margin:0">${esc(subtitle)}</p>` : ''}</div>
    ${action || ''}
  </div>`;
}

export function emptyState(title, body, cta) {
  return `<div class="empty-state">
    <h2>${esc(title)}</h2>
    <p>${esc(body)}</p>
    ${cta || ''}
  </div>`;
}

export { esc, money, el };
