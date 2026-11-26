// Express application assembly. Exported separately from server.js so tests can
// mount the full app with an in-memory database without opening a socket.
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { attachUser } from './middleware/auth.js';
import { errorHandler, notFoundHandler, requestLogger } from './middleware/errors.js';
import { csrfGuard, rateLimiter, securityHeaders } from './middleware/security.js';
import authRoutes from './routes/auth.js';
import productRoutes from './routes/products.js';
import cartRoutes from './routes/cart.js';
import orderRoutes from './routes/orders.js';
import adminRoutes from './routes/admin.js';
import { migrate, queryOne, driverName } from '../database/db.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..');
const PUBLIC_DIR = path.join(ROOT, 'frontend', 'public');

export async function createApp() {
  await migrate();

  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', 1);

  app.use(securityHeaders());
  app.use(express.json({ limit: '128kb' }));
  app.use(express.urlencoded({ extended: false, limit: '128kb' }));
  if (process.env.NODE_ENV !== 'test') app.use(requestLogger);
  app.use(rateLimiter({ windowMs: 60_000, max: Number(process.env.RATE_LIMIT_MAX || 300) }));

  app.get('/api/health', async (_req, res) => {
    const productCount = await queryOne('SELECT COUNT(*) AS total FROM products');
    res.json({
      status: 'ok',
      service: process.env.APP_NAME || 'Online Shopping Platform',
      database: driverName() || 'pending',
      product_count: productCount?.total ?? 0,
      timestamp: new Date().toISOString(),
    });
  });

  app.use(attachUser());

  app.use('/api', csrfGuard());
  app.use('/api/auth', authRoutes);
  app.use('/api/products', productRoutes);
  app.use('/api/cart', cartRoutes);
  app.use('/api/orders', orderRoutes);
  app.use('/api/admin', adminRoutes);

  // Static demo payment/invoice helpers are disabled by default.
  app.use(express.static(PUBLIC_DIR, { etag: true, maxAge: '1h', index: false }));

  // Single-page shell. Every non-API route returns the storefront document so
  // client-side hash routing can take over.
  const indexFile = path.join(PUBLIC_DIR, 'index.html');
  app.get(/^\/(?!api\/).*/, (req, res, next) => {
    if (!fs.existsSync(indexFile)) {
      return res.status(503).send('Frontend bundle not built yet. Run `npm run build`.');
    }
    if (req.path.includes('.')) return next();
    return res.sendFile(indexFile);
  });

  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}

export const paths = { ROOT, PUBLIC_DIR };
