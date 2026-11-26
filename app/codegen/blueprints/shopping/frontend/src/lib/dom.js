// Tiny DOM helpers used across views. Every value interpolated into HTML must
// pass through `esc` — the helpers never build markup from raw strings.
export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

export function money(cents) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(cents || 0) / 100);
}

export function el(selector, attrs = {}, children = []) {
  const [tag, classes] = selector.split('.');
  const node = document.createElement(tag || 'div');
  if (classes) node.className = classes.split('.').join(' ');
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'html') {
      node.innerHTML = value;
    } else if (key === 'text') {
      node.textContent = value;
    } else {
      node.setAttribute(key, value === true ? '' : String(value));
    }
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function toast(message, variant = 'info', timeout = 3600) {
  const stack = document.getElementById('toastStack');
  if (!stack) return;
  const node = el(`div.toast${variant === 'error' ? '.error' : variant === 'success' ? '.success' : ''}`, { role: 'status', text: message });
  stack.append(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transform = 'translateY(6px)';
    node.style.transition = 'opacity .2s, transform .2s';
    setTimeout(() => node.remove(), 220);
  }, timeout);
}

export function openModal(render) {
  const root = document.getElementById('modalRoot');
  const backdrop = el('div.modal-backdrop');
  const modal = el('div.modal', { role: 'dialog', 'aria-modal': 'true' });
  backdrop.append(modal);
  const close = () => { root.innerHTML = ''; };
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(); });
  document.addEventListener('keydown', function onKey(event) {
    if (event.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); }
  });
  render(modal, close);
  root.innerHTML = '';
  root.append(backdrop);
  const focusable = modal.querySelector('input, button, textarea, select');
  focusable?.focus();
  return close;
}

export function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
