// Migration entry point: `npm run db:migrate`
import { migrate, databasePath, driverName } from './db.js';

const started = Date.now();
await migrate();
console.log(`Schema applied to ${databasePath()} (${driverName() || 'driver pending'}) in ${Date.now() - started}ms`);
