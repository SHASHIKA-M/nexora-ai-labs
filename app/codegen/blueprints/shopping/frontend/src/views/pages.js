// Page controllers. Each export receives a context object and returns a cleanup
// function. All data comes from the real API — nothing is hard-coded.
import { catalog, cartApi, orderApi, adminApi } from '../lib/api.js';
import { esc, money, el, toast, formatDate, formatDateTime } from '../lib/dom.js';
import {
  productGrid, skeletonGrid, errorState, summaryCard, statusPill,
  mountAddToCart, hero, sectionHead, emptyState, setButtonBusy,
} from './store.js';
import { app } from '../main.js';

function mount(html) {
  const view = document.getElementById('view');
  view.innerHTML = html;
  return view;
}

function withCart(action) {
  return async (productId, button) => {
    try {
      setButtonBusy(button, true, 'Adding…');
      await action(productId);
      toast('Added to your bag', 'success');
      await app.refreshCart();
    } catch (error) {
      if (error.status === 401) {
        toast('Sign in to add items to your bag', 'info');
        location.hash = '#/account';
        return;
      }
      toast(error.message, 'error');
    } finally {
      setButtonBusy(button, false);
    }
  };
}

export async function shopPage(ctx) {
  const { query } = ctx;
  const category = query.get('category') || '';
  const searchTerm = query.get('q') || '';
  const sort = query.get('sort') || 'featured';
  mount(`
    <div class="section">
      <div class="section-head" style="margin-top:34px">
        <div>
          <p class="eyebrow">Catalogue</p>
          <h1>${category ? esc(category.replace(/^\w/, (c) => c.toUpperCase())) : 'Shop everything'}</h1>
          <p class="muted" id="resultCount" style="margin:0">Loading products…</p>
        </div>
        <form class="search" id="shopSearch" role="search" style="background:var(--panel)">
          <label class="sr-only" for="shopSearchInput">Search products</label>
          <input id="shopSearchInput" type="search" value="${esc(searchTerm)}" placeholder="Search…" style="padding-left:12px;width:180px">
          <button class="icon-btn" type="submit" aria-label="Search">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          </button>
        </form>
      </div>
      <div class="chip-row" id="categoryChips" style="margin-bottom:20px"></div>
      <div class="section-head" style="margin:0 0 16px">
        <div class="small muted" id="sortLabel"></div>
        <form id="sortForm">
          <label class="sr-only" for="sortSelect">Sort products</label>
          <select id="sortSelect" class="input" style="width:auto;padding:8px 12px">
            <option value="featured">Featured</option>
            <option value="newest">Newest</option>
            <option value="price-asc">Price: low to high</option>
            <option value="price-desc">Price: high to low</option>
            <option value="name">Name A–Z</option>
          </select>
        </form>
      </div>
      <div id="productResults">${skeletonGrid(8)}</div>
    </div>`);

  const sortSelect = document.getElementById('sortSelect');
  sortSelect.value = sort;
  sortSelect.addEventListener('change', () => {
    const params = new URLSearchParams(location.hash.split('?')[1] || '');
    params.set('sort', sortSelect.value);
    location.hash = `#/shop?${params.toString()}`;
  });

  document.getElementById('shopSearch').addEventListener('submit', (event) => {
    event.preventDefault();
    const params = new URLSearchParams(location.hash.split('?')[1] || '');
    const value = document.getElementById('shopSearchInput').value.trim();
    if (value) params.set('q', value); else params.delete('q');
    location.hash = `#/shop?${params.toString()}`;
  });

  let categories = [];
  try {
    const [products, categoryResponse] = await Promise.all([
      catalog.products({ category, search: searchTerm, sort }),
      catalog.categories(),
    ]);
    categories = categoryResponse.categories;
    const results = document.getElementById('productResults');
    if (!results) return () => {};
    results.innerHTML = productGrid(products.products);
    document.getElementById('resultCount').textContent =
      `${products.total} product${products.total === 1 ? '' : 's'}${searchTerm ? ` for “${searchTerm}”` : ''}`;
    document.getElementById('sortLabel').textContent = `Showing ${products.products.length} of ${products.total}`;

    const chips = document.getElementById('categoryChips');
    chips.innerHTML = [
      `<button class="chip" data-category="" aria-pressed="${category === ''}">All</button>`,
      ...categories.map((item) => `
        <button class="chip" data-category="${esc(item.slug)}" aria-pressed="${category === item.slug}">
          ${esc(item.name)} <span class="muted">(${item.product_count})</span>
        </button>`),
    ].join('');
    chips.addEventListener('click', (event) => {
      const chip = event.target.closest('[data-category]');
      if (!chip) return;
      const params = new URLSearchParams(location.hash.split('?')[1] || '');
      if (chip.dataset.category) params.set('category', chip.dataset.category);
      else params.delete('category');
      if (searchTerm) params.set('q', searchTerm);
      location.hash = `#/shop${params.toString() ? `?${params.toString()}` : ''}`;
    });

    const add = withCart((productId) => cartApi.add(productId, 1));
    mountAddToCart(results, add);
  } catch (error) {
    document.getElementById('productResults').innerHTML = errorState(error.message, 'retryShop');
    document.getElementById('retryShop')?.addEventListener('click', () => ctx.rerender());
  }
  return () => {};
}

export async function homePage(ctx) {
  mount(`
    ${hero()}
    <div class="section">
      <div id="featuredSection">${sectionHead('Featured pieces', 'Chosen by the studio this month')}
        ${skeletonGrid(4)}
      </div>
      <div id="categorySection"></div>
      <div id="newestSection">${sectionHead('New arrivals', 'The most recent additions to the collection')}
        ${skeletonGrid(4)}
      </div>
    </div>`);

  try {
    const [featured, newest, categoriesResponse] = await Promise.all([
      catalog.products({ sort: 'featured', limit: 4 }),
      catalog.products({ sort: 'newest', limit: 4 }),
      catalog.categories(),
    ]);
    document.getElementById('featuredSection').innerHTML =
      sectionHead('Featured pieces', 'Chosen by the studio this month',
        `<a class="btn ghost" href="#/shop">View all →</a>`) + productGrid(featured.products);
    document.getElementById('newestSection').innerHTML =
      sectionHead('New arrivals', 'The most recent additions to the collection',
        `<a class="btn ghost" href="#/shop?sort=newest">View all →</a>`) + productGrid(newest.products);

    document.getElementById('categorySection').innerHTML = `
      ${sectionHead('Shop by room', 'Five categories, twelve products, no filler')}
      <div class="product-grid" style="grid-template-columns:repeat(auto-fill,minmax(190px,1fr))">
        ${categoriesResponse.categories.map((category) => `
          <a class="card" href="#/shop?category=${esc(category.slug)}" style="display:block">
            <p class="product-kicker">${category.product_count} product${category.product_count === 1 ? '' : 's'}</p>
            <h3 style="margin:0 0 6px">${esc(category.name)}</h3>
            <p class="muted small" style="margin:0">${esc(category.description)}</p>
          </a>`).join('')}
      </div>`;

    mountAddToCart(document.getElementById('view'), withCart((productId) => cartApi.add(productId, 1)));
  } catch (error) {
    toast(error.message, 'error');
  }
  return () => {};
}

export async function productPage(ctx) {
  const { slug } = ctx.params;
  mount(`<div class="section" style="padding-top:40px">${skeletonGrid(1)}</div>`);
  const view = document.getElementById('view');
  try {
    const { product, related } = await catalog.product(slug);
    document.title = `${product.name} — Aurora & Co.`;
    view.innerHTML = `
      <div class="product-detail">
        <div class="detail-media">
          <img src="${esc(product.image)}" alt="${esc(product.name)}" width="640" height="640">
        </div>
        <div>
          <nav class="breadcrumb" aria-label="Breadcrumb">
            <a href="#/">Home</a><span>/</span>
            <a href="#/shop${product.category_slug ? `?category=${esc(product.category_slug)}` : ''}">${esc(product.category_name || 'Shop')}</a>
            <span>/</span><span>${esc(product.name)}</span>
          </nav>
          ${product.badge ? `<span class="badge" style="position:static;display:inline-block;margin-bottom:10px">${esc(product.badge)}</span>` : ''}
          <h1>${esc(product.name)}</h1>
          <div class="detail-price">${money(product.price_cents)}</div>
          <p class="muted">${esc(product.description)}</p>
          <div class="detail-actions">
            <div class="qty-control" id="qtyControl">
              <button type="button" data-qty="-1" aria-label="Decrease quantity">−</button>
              <span id="qtyValue" aria-live="polite">1</span>
              <button type="button" data-qty="1" aria-label="Increase quantity">+</button>
            </div>
            <button class="btn" id="addToBag" ${product.stock > 0 ? '' : 'disabled'}>
              ${product.stock > 0 ? 'Add to bag' : 'Sold out'}
            </button>
            <a class="btn secondary" href="#/cart">View bag</a>
          </div>
          <ul class="spec-list">
            <li><span>Availability</span><span>${product.stock > 0 ? `${product.stock} in stock` : 'Sold out'}</span></li>
            <li><span>Category</span><span>${esc(product.category_name || 'Collection')}</span></li>
            <li><span>Shipping</span><span>Free over $75, otherwise $6.50</span></li>
            <li><span>Returns</span><span>30 days, unused condition</span></li>
          </ul>
          <h3 style="margin-top:28px">Details</h3>
          <p class="muted">${esc(product.long_description || product.description)}</p>
        </div>
      </div>
      ${related.length ? `<div class="section">${sectionHead('You may also like', 'From the same collection')}${productGrid(related)}</div>` : ''}`;

    let quantity = 1;
    const qtyValue = document.getElementById('qtyValue');
    document.getElementById('qtyControl').addEventListener('click', (event) => {
      const button = event.target.closest('[data-qty]');
      if (!button) return;
      quantity = Math.min(99, Math.max(1, quantity + Number(button.dataset.qty)));
      qtyValue.textContent = String(quantity);
    });

    const add = withCart((productId) => cartApi.add(productId, quantity));
    document.getElementById('addToBag').addEventListener('click', (event) => add(product.id, event.currentTarget));
    mountAddToCart(view, withCart((productId) => cartApi.add(productId, 1)));
  } catch (error) {
    view.innerHTML = `<div class="section" style="padding-top:40px">${errorState(error.message, 'retryProduct')}</div>`;
    document.getElementById('retryProduct')?.addEventListener('click', () => ctx.rerender());
  }
  return () => { document.title = 'Aurora & Co. — Everyday objects, considered'; };
}

export async function cartPage(ctx) {
  if (!app.state.user) {
    location.hash = '#/account?next=cart';
    return () => {};
  }
  mount(`<div class="section" style="padding-top:34px"><h1>Your bag</h1><div class="spinner" style="margin:30px 0"></div></div>`);
  const view = document.getElementById('view');
  try {
    const cart = await cartApi.get();
    if (!cart.items.length) {
      view.innerHTML = `<div class="section" style="padding-top:34px">
        ${emptyState('Your bag is empty', 'Nothing here yet — the collection is a good place to start.', '<a class="btn" href="#/shop">Browse the shop</a>')}
      </div>`;
      return () => {};
    }
    view.innerHTML = `
      <div class="cart-layout">
        <div>
          <h1>Your bag</h1>
          <div class="small muted" style="margin-bottom:10px">${cart.item_count} item${cart.item_count === 1 ? '' : 's'}</div>
          <div id="cartLines">
            ${cart.items.map((line) => `
              <div class="cart-line" data-product="${line.product_id}">
                <a class="cart-thumb" href="#/product/${esc(line.slug)}"><img src="${esc(line.image)}" alt="${esc(line.name)}"></a>
                <div>
                  <h4><a href="#/product/${esc(line.slug)}">${esc(line.name)}</a></h4>
                  <p class="small muted" style="margin:0 0 8px">${money(line.price_cents)} each</p>
                  <div class="qty-control">
                    <button type="button" data-line-qty="-1" aria-label="Decrease ${esc(line.name)} quantity">−</button>
                    <span>${line.quantity}</span>
                    <button type="button" data-line-qty="1" aria-label="Increase ${esc(line.name)} quantity">+</button>
                  </div>
                  <button class="link-btn" style="margin-left:12px" data-remove="${line.product_id}">Remove</button>
                </div>
                <div class="line-total">
                  <strong>${money(line.line_total_cents)}</strong>
                  ${line.low_stock ? '<div class="small" style="color:var(--amber);margin-top:4px">Low stock</div>' : ''}
                </div>
              </div>`).join('')}
          </div>
          <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
            <a class="btn secondary" href="#/shop">Continue shopping</a>
          </div>
        </div>
        ${summaryCard(cart)}
      </div>`;

    const reload = () => ctx.rerender();
    view.addEventListener('click', async (event) => {
      const line = event.target.closest('[data-product]');
      if (!line) return;
      const productId = Number(line.dataset.product);
      const item = cart.items.find((entry) => entry.product_id === productId);
      try {
        if (event.target.closest('[data-remove]')) {
          await cartApi.remove(productId);
          toast('Removed from bag', 'success');
          await app.refreshCart();
          reload();
          return;
        }
        const qtyButton = event.target.closest('[data-line-qty]');
        if (qtyButton) {
          const next = item.quantity + Number(qtyButton.dataset.lineQty);
          if (next < 1) {
            await cartApi.remove(productId);
          } else {
            await cartApi.update(productId, next);
          }
          await app.refreshCart();
          reload();
        }
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  } catch (error) {
    view.innerHTML = `<div class="section" style="padding-top:34px">${errorState(error.message, 'retryCart')}</div>`;
    document.getElementById('retryCart')?.addEventListener('click', () => ctx.rerender());
  }
  return () => {};
}

export async function checkoutPage(ctx) {
  if (!app.state.user) {
    location.hash = '#/account?next=checkout';
    return () => {};
  }
  const view = mount(`<div class="section" style="padding-top:34px"><div class="spinner"></div></div>`);
  try {
    const cart = await cartApi.get();
    if (!cart.items.length) {
      view.innerHTML = `<div class="section">${emptyState('Nothing to check out', 'Your bag is empty.', '<a class="btn" href="#/shop">Browse the shop</a>')}</div>`;
      return () => {};
    }
    view.innerHTML = `
      <div class="checkout-layout">
        <div>
          <h1>Checkout</h1>
          <p class="muted small">This is a demo store — no card is charged. Order data is written to the real database.</p>
          <form id="checkoutForm" novalidate>
            <div class="card" style="margin-bottom:18px">
              <h3>Shipping details</h3>
              <div class="form-error" id="checkoutError" hidden></div>
              <div class="field-row">
                <div class="field"><label for="customer_name">Full name</label><input id="customer_name" name="customer_name" required value="${esc(app.state.user.name)}"></div>
                <div class="field"><label for="customer_email">Email</label><input id="customer_email" name="customer_email" type="email" required value="${esc(app.state.user.email)}"></div>
              </div>
              <div class="field"><label for="shipping_address">Street address</label><input id="shipping_address" name="shipping_address" required minlength="5" placeholder="12 Harbour Road, Apt 4B"></div>
              <div class="field-row">
                <div class="field"><label for="shipping_city">City</label><input id="shipping_city" name="shipping_city" required></div>
                <div class="field"><label for="shipping_postal">Postal code</label><input id="shipping_postal" name="shipping_postal" required></div>
              </div>
              <div class="field-row">
                <div class="field"><label for="shipping_country">Country</label><input id="shipping_country" name="shipping_country" required value="Singapore"></div>
                <div class="field"><label for="payment_method">Payment</label>
                  <select id="payment_method" name="payment_method">
                    <option value="demo_card">Demo card (simulated)</option>
                    <option value="bank_transfer">Bank transfer</option>
                    <option value="card_on_delivery">Card on delivery</option>
                  </select>
                </div>
              </div>
              <div class="field"><label for="notes">Delivery notes (optional)</label><textarea id="notes" name="notes" maxlength="500" placeholder="Leave with the concierge"></textarea></div>
            </div>
            <div class="card">
              <h3>Items</h3>
              ${cart.items.map((line) => `
                <div class="summary-row">
                  <span class="muted">${esc(line.name)} × ${line.quantity}</span>
                  <span>${money(line.line_total_cents)}</span>
                </div>`).join('')}
            </div>
            <button class="btn block" type="submit" style="margin-top:18px" id="placeOrderBtn">Place order · ${money(cart.total_cents)}</button>
          </form>
        </div>
        ${summaryCard(cart, { actionLabel: null })}
      </div>`;

    document.getElementById('checkoutForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = document.getElementById('placeOrderBtn');
      const errorBox = document.getElementById('checkoutError');
      errorBox.hidden = true;
      if (!form.checkValidity()) {
        errorBox.textContent = 'Please complete the required shipping fields.';
        errorBox.hidden = false;
        form.reportValidity();
        return;
      }
      const payload = Object.fromEntries(new FormData(form).entries());
      try {
        setButtonBusy(button, true, 'Placing order…');
        const result = await orderApi.create(payload);
        await app.refreshCart();
        toast(`Order ${result.order.reference} placed`, 'success');
        location.hash = `#/orders/${result.order.id}`;
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.hidden = false;
        setButtonBusy(button, false);
      }
    });
  } catch (error) {
    view.innerHTML = `<div class="section">${errorState(error.message, 'retryCheckout')}</div>`;
    document.getElementById('retryCheckout')?.addEventListener('click', () => ctx.rerender());
  }
  return () => {};
}

export async function ordersPage(ctx) {
  if (!app.state.user) {
    location.hash = '#/account?next=orders';
    return () => {};
  }
  const view = mount(`<div class="section" style="padding-top:34px"><h1>Your orders</h1><div class="spinner"></div></div>`);
  try {
    const { orders } = await orderApi.list();
    if (!orders.length) {
      view.innerHTML = `<div class="section" style="padding-top:34px"><h1>Your orders</h1>
        ${emptyState('No orders yet', 'When you place an order it will appear here with live status.', '<a class="btn" href="#/shop">Start shopping</a>')}</div>`;
      return () => {};
    }
    view.innerHTML = `<div class="section" style="padding-top:34px"><h1>Your orders</h1>
      ${orders.map((order) => `
        <article class="order-card">
          <div class="order-head">
            <div>
              <strong>${esc(order.reference)}</strong>
              <div class="small muted">${formatDate(order.created_at)} · ${order.item_count} item${order.item_count === 1 ? '' : 's'}</div>
            </div>
            <div style="display:flex;align-items:center;gap:12px">
              ${statusPill(order.status)}
              <strong>${money(order.total_cents)}</strong>
              <a class="btn small secondary" href="#/orders/${order.id}">View</a>
            </div>
          </div>
        </article>`).join('')}
    </div>`;
  } catch (error) {
    view.innerHTML = `<div class="section" style="padding-top:34px">${errorState(error.message, 'retryOrders')}</div>`;
    document.getElementById('retryOrders')?.addEventListener('click', () => ctx.rerender());
  }
  return () => {};
}

export async function orderDetailPage(ctx) {
  if (!app.state.user) {
    location.hash = '#/account?next=orders';
    return () => {};
  }
  const view = mount(`<div class="section" style="padding-top:34px"><div class="spinner"></div></div>`);
  try {
    const { order, items, events } = await orderApi.get(ctx.params.id);
    view.innerHTML = `<div class="section" style="padding-top:34px">
      <nav class="breadcrumb"><a href="#/orders">Orders</a><span>/</span><span>${esc(order.reference)}</span></nav>
      <div class="order-head" style="margin-bottom:6px">
        <h1 style="margin:0">${esc(order.reference)}</h1>
        ${statusPill(order.status)}
      </div>
      <p class="muted small">Placed ${formatDateTime(order.created_at)} · ${esc(order.payment_method.replace(/_/g, ' '))}</p>
      <div class="cart-layout" style="padding:0">
        <div>
          <div class="card">
            <h3>Items</h3>
            ${items.map((item) => `
              <div class="summary-row"><span class="muted">${esc(item.product_name)} × ${item.quantity}</span><span>${money(item.unit_price_cents * item.quantity)}</span></div>`).join('')}
            <div class="summary-row"><span class="muted">Subtotal</span><span>${money(order.subtotal_cents)}</span></div>
            <div class="summary-row"><span class="muted">Shipping</span><span>${order.shipping_cents === 0 ? 'Free' : money(order.shipping_cents)}</span></div>
            <div class="summary-row total"><span>Total</span><span>${money(order.total_cents)}</span></div>
          </div>
          <div class="card" style="margin-top:16px">
            <h3>Shipping to</h3>
            <p class="muted small" style="margin:0;white-space:pre-line">${esc(order.customer_name)}
${esc(order.shipping_address)}
${esc(order.shipping_city)} ${esc(order.shipping_postal)}
${esc(order.shipping_country)}</p>
            ${order.notes ? `<p class="small muted" style="margin-top:10px">Note: ${esc(order.notes)}</p>` : ''}
          </div>
        </div>
        <div>
          <div class="card">
            <h3>Status timeline</h3>
            <ul class="timeline">
              ${[...events].reverse().map((event) => `
                <li><time>${formatDateTime(event.created_at)}</time><span>${esc(event.status)} — ${esc(event.note)}</span></li>`).join('')}
            </ul>
          </div>
          ${['pending', 'paid'].includes(order.status) ? `
            <button class="btn danger block" id="cancelOrder" style="margin-top:14px">Cancel order</button>` : ''}
          <a class="btn secondary block" href="#/shop" style="margin-top:10px">Continue shopping</a>
        </div>
      </div>
    </div>`;

    document.getElementById('cancelOrder')?.addEventListener('click', async (event) => {
      if (!confirm('Cancel this order? Stock will be returned to the catalogue.')) return;
      try {
        setButtonBusy(event.currentTarget, true, 'Cancelling…');
        await orderApi.cancel(order.id);
        toast('Order cancelled', 'success');
        ctx.rerender();
      } catch (error) {
        toast(error.message, 'error');
        setButtonBusy(event.currentTarget, false);
      }
    });
  } catch (error) {
    view.innerHTML = `<div class="section" style="padding-top:34px">${errorState(error.message, 'retryOrder')}</div>`;
    document.getElementById('retryOrder')?.addEventListener('click', () => ctx.rerender());
  }
  return () => {};
}

export function accountPage(ctx) {
  const next = ctx.query.get('next');
  if (app.state.user && !next) {
    location.hash = '#/orders';
    return () => {};
  }
  const view = mount(`
    <div class="auth-wrap">
      <div class="card auth-card">
        <h1 style="margin-bottom:4px">${app.state.user ? 'Your account' : 'Welcome back'}</h1>
        <p class="muted small">${app.state.user ? 'You are signed in.' : 'Sign in to save your bag, place orders and track deliveries.'}</p>
        ${app.state.user ? `
          <ul class="spec-list" style="margin-top:18px">
            <li><span>Name</span><span>${esc(app.state.user.name)}</span></li>
            <li><span>Email</span><span>${esc(app.state.user.email)}</span></li>
            <li><span>Role</span><span>${esc(app.state.user.role)}</span></li>
          </ul>
          <div style="display:flex;gap:10px;margin-top:20px;flex-wrap:wrap">
            <a class="btn" href="#/orders">View orders</a>
            ${app.state.user.role === 'admin' ? '<a class="btn secondary" href="#/admin">Admin dashboard</a>' : ''}
            <button class="btn secondary" id="signOut">Sign out</button>
          </div>` : `
          <div class="auth-tabs" role="tablist">
            <button role="tab" aria-selected="true" data-tab="login">Sign in</button>
            <button role="tab" aria-selected="false" data-tab="register">Create account</button>
          </div>
          <div id="authPanel"></div>
          <div class="demo-hint">
            <strong>Demo accounts</strong><br>
            Customer — demo@shop.test / Demo1234!<br>
            Admin — admin@shop.test / Admin1234!
          </div>`}
      </div>
    </div>`);

  document.getElementById('signOut')?.addEventListener('click', async () => {
    await app.logout();
  });

  if (app.state.user) return () => {};

  const panel = document.getElementById('authPanel');
  const renderForm = (mode) => {
    panel.innerHTML = `
      <form id="authForm" novalidate>
        <div class="form-error" id="authError" hidden></div>
        ${mode === 'register' ? `
          <div class="field"><label for="authName">Full name</label><input id="authName" name="name" required minlength="2" autocomplete="name"></div>` : ''}
        <div class="field"><label for="authEmail">Email</label><input id="authEmail" name="email" type="email" required autocomplete="email"></div>
        <div class="field"><label for="authPassword">Password</label><input id="authPassword" name="password" type="password" required minlength="8" autocomplete="${mode === 'register' ? 'new-password' : 'current-password'}"></div>
        <button class="btn block" type="submit" id="authSubmit">${mode === 'register' ? 'Create account' : 'Sign in'}</button>
      </form>`;
    panel.querySelector('#authForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const data = Object.fromEntries(new FormData(form).entries());
      const errorBox = document.getElementById('authError');
      const button = document.getElementById('authSubmit');
      errorBox.hidden = true;
      try {
        setButtonBusy(button, true, mode === 'register' ? 'Creating account…' : 'Signing in…');
        if (mode === 'register') await app.register(data);
        else await app.login(data);
        toast(mode === 'register' ? 'Account created' : `Welcome back, ${app.state.user?.name || ''}`.trim(), 'success');
        const destination = next ? `#/${next}` : (app.state.user?.role === 'admin' ? '#/admin' : '#/orders');
        location.hash = destination;
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.hidden = false;
        setButtonBusy(button, false);
      }
    });
  };

  renderForm(next === 'register' ? 'register' : 'login');
  view.querySelector('.auth-tabs').addEventListener('click', (event) => {
    const tab = event.target.closest('[data-tab]');
    if (!tab) return;
    view.querySelectorAll('.auth-tabs button').forEach((button) => {
      button.setAttribute('aria-selected', String(button === tab));
    });
    renderForm(tab.dataset.tab);
  });
  return () => {};
}

export async function adminPage(ctx) {
  if (!app.state.user) {
    location.hash = '#/account?next=admin';
    return () => {};
  }
  if (app.state.user.role !== 'admin') {
    mount(`<div class="section" style="padding-top:34px">${emptyState('Administrator access required', 'Sign in with an admin account to open the dashboard.', '<a class="btn" href="#/account">Switch account</a>')}</div>`);
    return () => {};
  }

  const view = mount(`
    <div class="admin-wrap">
      <p class="eyebrow">Operations</p>
      <h1>Admin dashboard</h1>
      <div id="adminStats" class="stat-grid"></div>
      <div class="tabs" role="tablist">
        <button role="tab" aria-selected="true" data-admin-tab="orders">Orders</button>
        <button role="tab" aria-selected="false" data-admin-tab="products">Products</button>
        <button role="tab" aria-selected="false" data-admin-tab="customers">Customers</button>
      </div>
      <div id="adminPanel"><div class="spinner"></div></div>
    </div>`);

  const panel = document.getElementById('adminPanel');

  async function loadStats() {
    try {
      const stats = await adminApi.stats();
      document.getElementById('adminStats').innerHTML = `
        <div class="stat"><div class="label">Revenue</div><div class="value">${money(stats.revenue_cents)}</div></div>
        <div class="stat"><div class="label">Orders</div><div class="value">${stats.order_count}</div></div>
        <div class="stat"><div class="label">Customers</div><div class="value">${stats.customer_count}</div></div>
        <div class="stat"><div class="label">Low stock</div><div class="value">${stats.low_stock.length}</div></div>`;
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function loadOrders() {
    panel.innerHTML = '<div class="spinner"></div>';
    try {
      const { orders } = await adminApi.orders();
      panel.innerHTML = `<div class="table-wrap card" style="padding:0">
        <table class="data-table">
          <thead><tr><th>Reference</th><th>Customer</th><th>Items</th><th>Total</th><th>Placed</th><th>Status</th></tr></thead>
          <tbody>
            ${orders.map((order) => `
              <tr>
                <td><a href="#/orders/${order.id}" style="color:var(--gold-soft)">${esc(order.reference)}</a></td>
                <td>${esc(order.customer_name)}<div class="small muted">${esc(order.customer_email)}</div></td>
                <td>${order.item_count ?? 0}</td>
                <td>${money(order.total_cents)}</td>
                <td class="small muted">${formatDate(order.created_at)}</td>
                <td>
                  <label class="sr-only" for="status-${order.id}">Status for ${esc(order.reference)}</label>
                  <select id="status-${order.id}" data-order-status="${order.id}">
                    ${['pending', 'paid', 'packed', 'shipped', 'delivered', 'cancelled'].map((status) =>
                      `<option value="${status}" ${status === order.status ? 'selected' : ''}>${status}</option>`).join('')}
                  </select>
                </td>
              </tr>`).join('') || '<tr><td colspan="6" class="muted">No orders yet.</td></tr>'}
          </tbody>
        </table>
      </div>`;
      panel.addEventListener('change', async (event) => {
        const select = event.target.closest('[data-order-status]');
        if (!select) return;
        try {
          await adminApi.setStatus(Number(select.dataset.orderStatus), select.value, 'Updated by admin dashboard.');
          toast('Order status updated', 'success');
          loadStats();
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    } catch (error) {
      panel.innerHTML = errorState(error.message, 'retryAdminOrders');
    }
  }

  async function loadProducts() {
    panel.innerHTML = '<div class="spinner"></div>';
    try {
      const { products } = await adminApi.products();
      panel.innerHTML = `
        <div class="table-wrap card" style="padding:0">
          <table class="data-table">
            <thead><tr><th>Product</th><th>Price (cents)</th><th>Stock</th><th>Active</th><th></th></tr></thead>
            <tbody>
              ${products.map((product) => `
                <tr data-product-row="${product.id}">
                  <td>${esc(product.name)}<div class="small muted">${esc(product.slug)}</div></td>
                  <td><input class="input" style="width:110px;padding:6px 8px" type="number" min="0" value="${product.price_cents}" data-field="price_cents" aria-label="Price in cents for ${esc(product.name)}"></td>
                  <td><input class="input" style="width:90px;padding:6px 8px" type="number" min="0" value="${product.stock}" data-field="stock" aria-label="Stock for ${esc(product.name)}"></td>
                  <td><input type="checkbox" ${product.is_active ? 'checked' : ''} data-field="is_active" aria-label="Active for ${esc(product.name)}"></td>
                  <td><button class="btn small secondary" data-save-product="${product.id}">Save</button></td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
        <form class="card" id="newProductForm" style="margin-top:18px">
          <h3>Add a product</h3>
          <div class="field-row">
            <div class="field"><label for="newName">Name</label><input id="newName" name="name" required></div>
            <div class="field"><label for="newPrice">Price (cents)</label><input id="newPrice" name="price_cents" type="number" min="1" required></div>
          </div>
          <div class="field-row">
            <div class="field"><label for="newStock">Stock</label><input id="newStock" name="stock" type="number" min="0" value="10" required></div>
            <div class="field"><label for="newDesc">Description</label><input id="newDesc" name="description"></div>
          </div>
          <button class="btn" type="submit">Create product</button>
        </form>`;

      panel.addEventListener('click', async (event) => {
        const save = event.target.closest('[data-save-product]');
        if (!save) return;
        const row = save.closest('[data-product-row]');
        const payload = {
          price_cents: Number(row.querySelector('[data-field="price_cents"]').value),
          stock: Number(row.querySelector('[data-field="stock"]').value),
          is_active: row.querySelector('[data-field="is_active"]').checked,
        };
        try {
          setButtonBusy(save, true, 'Saving…');
          await adminApi.updateProduct(Number(save.dataset.saveProduct), payload);
          toast('Product updated', 'success');
          loadStats();
        } catch (error) {
          toast(error.message, 'error');
        } finally {
          setButtonBusy(save, false);
        }
      });

      panel.querySelector('#newProductForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.currentTarget).entries());
        try {
          const button = event.currentTarget.querySelector('button[type="submit"]');
          setButtonBusy(button, true, 'Creating…');
          await adminApi.createProduct({
            name: data.name,
            price_cents: Number(data.price_cents),
            stock: Number(data.stock),
            description: data.description,
          });
          toast('Product created', 'success');
          loadProducts();
          loadStats();
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    } catch (error) {
      panel.innerHTML = errorState(error.message, 'retryAdminProducts');
    }
  }

  async function loadCustomers() {
    panel.innerHTML = '<div class="spinner"></div>';
    try {
      const { customers } = await adminApi.customers();
      panel.innerHTML = `<div class="table-wrap card" style="padding:0">
        <table class="data-table">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Orders</th><th>Joined</th></tr></thead>
          <tbody>${customers.map((customer) => `
            <tr><td>${esc(customer.name)}</td><td class="muted">${esc(customer.email)}</td><td>${esc(customer.role)}</td>
            <td>${customer.order_count}</td><td class="small muted">${formatDate(customer.created_at)}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } catch (error) {
      panel.innerHTML = errorState(error.message, 'retryAdminCustomers');
    }
  }

  const loaders = { orders: loadOrders, products: loadProducts, customers: loadCustomers };
  view.querySelector('.tabs').addEventListener('click', (event) => {
    const tab = event.target.closest('[data-admin-tab]');
    if (!tab) return;
    view.querySelectorAll('[data-admin-tab]').forEach((button) => button.setAttribute('aria-selected', String(button === tab)));
    loaders[tab.dataset.adminTab]();
  });

  loadStats();
  loadOrders();
  return () => {};
}

export function notFoundPage() {
  mount(`<div class="section" style="padding-top:40px">${emptyState('Page not found', 'That link does not exist in this storefront.', '<a class="btn" href="#/">Back to the shop</a>')}</div>`);
  return () => {};
}

