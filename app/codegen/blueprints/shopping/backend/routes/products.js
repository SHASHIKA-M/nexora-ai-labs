import { Router } from 'express';
import { listProducts, listCategories, getProductBySlug } from '../services/catalogService.js';

const router = Router();

router.get('/categories', async (_req, res, next) => {
  try {
    res.json({ categories: await listCategories() });
  } catch (error) {
    next(error);
  }
});

router.get('/', async (req, res, next) => {
  try {
    const result = await listProducts({
      category: req.query.category,
      search: req.query.search,
      sort: req.query.sort,
      limit: req.query.limit,
      offset: req.query.offset,
    });
    res.json(result);
  } catch (error) {
    next(error);
  }
});

router.get('/:slug', async (req, res, next) => {
  try {
    res.json(await getProductBySlug(req.params.slug));
  } catch (error) {
    next(error);
  }
});

export default router;
