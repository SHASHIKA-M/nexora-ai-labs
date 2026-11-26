// Application shell: auth state, hash router, cart badge, global handlers.
import { auth, cartApi } from './lib/api.js';
import { toast } from './lib/dom.js';
import {
  homePage, shopPage, productPage, cartPage, checkoutPage,
  ordersPage, orderDetailPage, accountPage, adminPage, notFoundPage,
} from './views/pages.js';

export const app = {
  state: { user: null, cartCount: 0 },
  async refreshCart() {
    if (!this.state.user) {
      this.state.cartCount = 0;
      paintCartCount(0);
      return;
    }
    try {
      const cart = await cartApi.get();
      this.state.cartCount = cart.item_count;
      paintCartCount(cart.item_count);
    } catch {
      paintCartCount(0);
    }
  },
  async login(credentials) {
    const result = await auth.login(credentials);
    this.state.user = result.user;
    paintAccount();
    await this.refreshCart();
    return result;
  },
  async register(payload) {
    const result = await auth.register(payload);
    this.state.user = result.user;
    paintAccount();
    await this.refreshCart();
    return result;
  },
  async logout() {
    await auth.logout().catch(() => {});
    this.state.user = null;
    paintAccount();
    paintCartCount(0);
    toast('Signed out', 'success');
    location.hash = '#/';
  },
};

let currentCleanup = () => {};

function paintCartCount(count) {
  const badge = document.getElementById('cartCount');
  if (!badge) return;
  badge.textContent = String(count);
  badge.hidden = count <= 0;
}

function paintAccount() {
  const label = document.getElementById('accountLabel');
  const link = document.getElementById('accountLink');
  if (!label || !link) return;
  if (app.state.user) {
    label.textContent = app.state.user.name.split(' ')[0];
    link.setAttribute('aria-label', `Account: ${app.state.user.name}`);
    if (app.state.user.role === 'admin') {
      link.setAttribute('href', '#/admin');
    } else {
      link.setAttribute('href', '#/account');
    }
  } else {
    label.textContent = 'Sign in';
    link.setAttribute('href', '#/account');
    link.setAttribute('aria-label', 'Sign in');
  }
}

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, search] = raw.split('?');
  const segments = path.split('/').filter(Boolean);
  return { path, segments, query: new URLSearchParams(search || '') };
}

const ROUTES = [
  { match: (s) => s.length === 0, page: homePage, nav: 'shop' },
  { match: (s) => s[0] === 'shop', page: shopPage, nav: 'shop' },
  { match: (s) => s[0] === 'product' && s[1], page: productPage, params: (s) => ({ slug: decodeURIComponent(s[1]) }) },
  { match: (s) => s[0] === 'cart', page: cartPage },
  { match: (s) => s[0] === 'checkout', page: checkoutPage },
  { match: (s) => s[0] === 'orders' && s[1], page: orderDetailPage, params: (s) => ({ id: s[1] }) },
  { match: (s) => s[0] === 'orders', page: ordersPage },
  { match: (s) => s[0] === 'account', page: accountPage },
  { match: (s) => s[0] === 'admin', page: adminPage },
];

async function renderRoute() {
  const { segments, query } = parseHash();
  const route = ROUTES.find((candidate) => candidate.match(segments));
  const loading = document.getElementById('viewLoading');
  const view = document.getElementById('view');

  try {
    currentCleanup();
  } catch (error) {
    console.error('Cleanup failed', error);
  }
  currentCleanup = () => {};

  document.querySelectorAll('[data-nav]').forEach((link) => link.removeAttribute('aria-current'));
  const navKey = segments[0] === 'product' ? 'shop' : segments[0] || 'shop';
  document.querySelector(`[data-nav="${navKey}"]`)?.setAttribute('aria-current', 'page');

  document.getElementById('primaryNav')?.classList.remove('open');
  document.getElementById('navToggle')?.setAttribute('aria-expanded', 'false');

  try {
    const ctx = {
      params: route?.params ? route.params(segments) : {},
      query,
      rerender: renderRoute,
    };
    const cleanup = await (route ? route.page(ctx) : notFoundPage());
    if (typeof cleanup === 'function') currentCleanup = cleanup;
    try {
      if (typeof window.scrollTo === 'function') window.scrollTo({ top: 0, behavior: 'auto' });
    } catch {
      // Scrolling is a nicety; never let it break a route transition.
    }
  } catch (error) {
    console.error(error);
    if (view) {
      view.innerHTML = `<div class="section" style="padding-top:40px">
        <div class="empty-state"><h2>Something went wrong</h2><p>${String(error.message || error)}</p>
        <a class="btn" href="#/">Return home</a></div></div>`;
    }
  } finally {
    if (loading) loading.hidden = true;
  }
}

function wireChrome() {
  const toggle = document.getElementById('navToggle');
  const nav = document.getElementById('primaryNav');
  toggle?.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
  });

  document.getElementById('searchForm')?.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = document.getElementById('searchInput');
    const term = input.value.trim();
    location.hash = term ? `#/shop?q=${encodeURIComponent(term)}` : '#/shop';
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      const input = document.getElementById('searchInput');
      if (input && input.offsetParent !== null) {
        event.preventDefault();
        input.focus();
      }
    }
  });
}

async function boot() {
  wireChrome();
  try {
    const { user } = await auth.me();
    app.state.user = user;
  } catch {
    app.state.user = null;
  }
  paintAccount();
  await app.refreshCart();
  window.addEventListener('hashchange', renderRoute);
  // Normalise the URL without firing hashchange, so the first render happens
  // exactly once (setting location.hash here would render the page twice and
  // double every API call made during boot).
  if (!location.hash) window.history.replaceState(null, '', `${location.pathname}#/`);
  await renderRoute();
  document.getElementById('buildStamp').textContent =
    `generated by NEXORA AI LABS · ${new Date().getFullYear()}`;
}

boot().catch((error) => {
  console.error(error);
  const container = document.getElementById('view');
  if (container) {
    container.innerHTML = `<div class="section" style="padding-top:40px">
      <div class="empty-state"><h2>The storefront failed to start</h2><p>${String(error.message || error)}</p></div></div>`;
  }
  document.getElementById('viewLoading').hidden = true;
});
