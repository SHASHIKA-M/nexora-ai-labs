import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import { getCart, addItem, updateItem, removeItem } from '../services/cartService.js';
import { requireInt } from '../lib/validate.js';

const router = Router();
router.use(requireAuth);

router.get('/', async (req, res, next) => {
  try {
    res.json(await getCart(req.user.id));
  } catch (error) {
    next(error);
  }
});

router.post('/items', async (req, res, next) => {
  try {
    const productId = requireInt(req.body?.product_id, 'Product', { min: 1, max: 1_000_000 });
    const quantity = requireInt(req.body?.quantity ?? 1, 'Quantity', { min: 1, max: 99 });
    res.status(201).json(await addItem(req.user.id, productId, quantity));
  } catch (error) {
    next(error);
  }
});

router.patch('/items/:productId', async (req, res, next) => {
  try {
    const productId = requireInt(req.params.productId, 'Product', { min: 1, max: 1_000_000 });
    const quantity = requireInt(req.body?.quantity, 'Quantity', { min: 1, max: 99 });
    res.json(await updateItem(req.user.id, productId, quantity));
  } catch (error) {
    next(error);
  }
});

router.delete('/items/:productId', async (req, res, next) => {
  try {
    const productId = requireInt(req.params.productId, 'Product', { min: 1, max: 1_000_000 });
    res.json(await removeItem(req.user.id, productId));
  } catch (error) {
    next(error);
  }
});

export default router;
