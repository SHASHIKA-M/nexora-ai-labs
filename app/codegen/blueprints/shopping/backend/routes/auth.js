import { Router } from 'express';
import { authenticate, registerUser } from '../services/userService.js';
import { createSession, sessionCookie, clearCookie, destroySession, extractToken, requireAuth } from '../middleware/auth.js';
import { rateLimiter } from '../middleware/security.js';

const router = Router();

const authLimiter = rateLimiter({
  windowMs: 10 * 60_000,
  max: 20,
  key: (req) => `auth:${req.ip}`,
});

router.post('/register', authLimiter, async (req, res, next) => {
  try {
    const user = await registerUser(req.body ?? {});
    const session = await createSession(user.id);
    res.setHeader('Set-Cookie', sessionCookie(session.token, session.expiresAt));
    res.status(201).json({ user, token: session.token });
  } catch (error) {
    next(error);
  }
});

router.post('/login', authLimiter, async (req, res, next) => {
  try {
    const user = await authenticate(req.body ?? {});
    const session = await createSession(user.id);
    res.setHeader('Set-Cookie', sessionCookie(session.token, session.expiresAt));
    res.json({ user, token: session.token });
  } catch (error) {
    next(error);
  }
});

router.post('/logout', async (req, res, next) => {
  try {
    await destroySession(extractToken(req));
    res.setHeader('Set-Cookie', clearCookie());
    res.json({ ok: true });
  } catch (error) {
    next(error);
  }
});

router.get('/me', (req, res) => {
  res.json({ user: req.user ?? null });
});

router.use(requireAuth);

router.get('/session', (req, res) => {
  res.json({ user: req.user, expires: 'rolling' });
});

export default router;
