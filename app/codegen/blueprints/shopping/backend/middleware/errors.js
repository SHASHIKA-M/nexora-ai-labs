import { HttpError } from '../lib/validate.js';

export function notFoundHandler(req, res) {
  if (req.path.startsWith('/api/')) {
    res.status(404).json({ error: 'Not found', path: req.originalUrl });
    return;
  }
  res.status(404).send('Not found');
}

export function errorHandler(error, req, res, _next) {
  const status = error instanceof HttpError ? error.status : 500;
  const payload = {
    error: error instanceof HttpError ? error.message : 'Something went wrong. Please try again.',
    details: error instanceof HttpError ? error.details : undefined,
  };
  if (status >= 500) {
    console.error(`[error] ${req.method} ${req.originalUrl}:`, error);
  }
  res.status(status).json(payload);
}

export function requestLogger(req, res, next) {
  const started = Date.now();
  res.on('finish', () => {
    if (process.env.NODE_ENV === 'test') return;
    console.log(`${req.method} ${req.originalUrl} ${res.statusCode} ${Date.now() - started}ms`);
  });
  next();
}
