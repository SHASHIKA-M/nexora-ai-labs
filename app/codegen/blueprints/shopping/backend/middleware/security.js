// Security headers, CSRF guard, body limits and a lightweight rate limiter.
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export function securityHeaders() {
  const csp = [
    "default-src 'self'",
    "img-src 'self' data: blob: https:",
    "style-src 'self' 'unsafe-inline'",
    "script-src 'self'",
    "connect-src 'self'",
    "frame-ancestors 'self'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ');
  return (req, res, next) => {
    res.setHeader('Content-Security-Policy', csp);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    res.setHeader('X-Frame-Options', 'SAMEORIGIN');
    res.setHeader('Permissions-Policy', 'geolocation=(), microphone=(), camera=()');
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    if (req.secure || req.get('x-forwarded-proto') === 'https') {
      res.setHeader('Strict-Transport-Security', 'max-age=15552000; includeSubDomains');
    }
    next();
  };
}

// SameSite=Lax cookies already block most cross-site writes, but API clients
// using bearer tokens are unaffected by this guard.
export function csrfGuard() {
  return (req, res, next) => {
    if (SAFE_METHODS.has(req.method)) return next();
    if (req.get('authorization')) return next();
    const origin = req.get('origin');
    if (!origin) return next(); // non-browser client without Origin header
    const host = req.get('host');
    let originHost = '';
    try {
      originHost = new URL(origin).host;
    } catch {
      return res.status(403).json({ error: 'Invalid request origin.' });
    }
    if (originHost !== host) {
      return res.status(403).json({ error: 'Cross-site request blocked.' });
    }
    return next();
  };
}

export function rateLimiter({ windowMs = 60_000, max = 60, key = (req) => req.ip } = {}) {
  const hits = new Map();
  const timer = setInterval(() => {
    const now = Date.now();
    for (const [bucket, entry] of hits) {
      if (entry.reset < now) hits.delete(bucket);
    }
  }, Math.max(windowMs, 30_000));
  timer.unref?.();

  return (req, res, next) => {
    const bucket = key(req);
    const now = Date.now();
    const entry = hits.get(bucket) ?? { count: 0, reset: now + windowMs };
    if (entry.reset < now) {
      entry.count = 0;
      entry.reset = now + windowMs;
    }
    entry.count += 1;
    hits.set(bucket, entry);
    res.setHeader('X-RateLimit-Limit', String(max));
    res.setHeader('X-RateLimit-Remaining', String(Math.max(0, max - entry.count)));
    if (entry.count > max) {
      res.setHeader('Retry-After', String(Math.ceil((entry.reset - now) / 1000)));
      return res.status(429).json({ error: 'Too many requests. Please slow down and try again shortly.' });
    }
    return next();
  };
}
