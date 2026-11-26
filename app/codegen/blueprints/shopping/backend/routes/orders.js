import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import { placeOrder, listOrdersForUser, getOrder, cancelOrder } from '../services/orderService.js';
import { requireInt } from '../lib/validate.js';

const router = Router();
router.use(requireAuth);

router.get('/', async (req, res, next) => {
  try {
    res.json({ orders: await listOrdersForUser(req.user.id) });
  } catch (error) {
    next(error);
  }
});

router.post('/', async (req, res, next) => {
  try {
    res.status(201).json(await placeOrder(req.user.id, req.body ?? {}));
  } catch (error) {
    next(error);
  }
});

router.get('/:id', async (req, res, next) => {
  try {
    const id = requireInt(req.params.id, 'Order', { min: 1, max: 1_000_000 });
    res.json(await getOrder(id, { userId: req.user.id, isAdmin: req.user.role === 'admin' }));
  } catch (error) {
    next(error);
  }
});

router.post('/:id/cancel', async (req, res, next) => {
  try {
    const id = requireInt(req.params.id, 'Order', { min: 1, max: 1_000_000 });
    res.json(await cancelOrder(req.user.id, id));
  } catch (error) {
    next(error);
  }
});

export default router;
