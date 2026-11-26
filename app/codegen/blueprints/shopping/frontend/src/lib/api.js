// Thin fetch wrapper: JSON in, JSON out, structured errors, credentials included.
//
// Requests are resolved against the <base> of the document rather than the
// server root. That keeps the same bundle working when the application is
// served from "/" and when NEXORA serves it from a preview sub-path such as
// "/preview/my-project/".
let csrfToken = null;

export function apiUrl(path) {
  const base = document.baseURI || window.location.href;
  return new URL(String(path).replace(/^\/+/, ''), base).toString();
}

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken;

  const response = await fetch(apiUrl(path), {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  let payload = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    payload = await response.json().catch(() => null);
  }
  if (!response.ok) {
    throw new ApiError(payload?.error || `Request failed (${response.status})`, response.status, payload?.details);
  }
  return payload;
}

export const api = {
  get: (path, options) => request(path, options),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body }),
  patch: (path, body, options = {}) => request(path, { ...options, method: 'PATCH', body }),
  delete: (path, options = {}) => request(path, { ...options, method: 'DELETE' }),
};

export const auth = {
  me: () => api.get('/api/auth/me'),
  login: (credentials) => api.post('/api/auth/login', credentials),
  register: (payload) => api.post('/api/auth/register', payload),
  logout: () => api.post('/api/auth/logout', {}),
};

export const catalog = {
  products: (params = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') search.set(key, value);
    }
    const query = search.toString();
    return api.get(`/api/products${query ? `?${query}` : ''}`);
  },
  product: (slug) => api.get(`/api/products/${encodeURIComponent(slug)}`),
  categories: () => api.get('/api/products/categories'),
};

export const cartApi = {
  get: () => api.get('/api/cart'),
  add: (productId, quantity = 1) => api.post('/api/cart/items', { product_id: productId, quantity }),
  update: (productId, quantity) => api.patch(`/api/cart/items/${productId}`, { quantity }),
  remove: (productId) => api.delete(`/api/cart/items/${productId}`),
};

export const orderApi = {
  list: () => api.get('/api/orders'),
  get: (id) => api.get(`/api/orders/${id}`),
  create: (payload) => api.post('/api/orders', payload),
  cancel: (id) => api.post(`/api/orders/${id}/cancel`, {}),
};

export const adminApi = {
  stats: () => api.get('/api/admin/stats'),
  orders: (status) => api.get(`/api/admin/orders${status ? `?status=${status}` : ''}`),
  order: (id) => api.get(`/api/admin/orders/${id}`),
  setStatus: (id, status, note) => api.post(`/api/admin/orders/${id}/status`, { status, note }),
  customers: () => api.get('/api/admin/customers'),
  products: () => api.get('/api/admin/products'),
  updateProduct: (id, payload) => api.patch(`/api/admin/products/${id}`, payload),
  createProduct: (payload) => api.post('/api/admin/products', payload),
};

export function setCsrfToken(token) {
  csrfToken = token;
}
