// HTTP entry point: `npm start`
import './lib/env.js';
import { createApp } from './app.js';
import { databasePath } from '../database/db.js';

const port = Number(process.env.PORT || 3000);

const app = await createApp();

const server = app.listen(port, '0.0.0.0', () => {
  console.log(`\n  ${process.env.APP_NAME || 'Online Shopping Platform'} is running`);
  console.log(`  Local:    http://localhost:${port}`);
  console.log(`  Database: ${databasePath()}`);
  console.log(`  Health:   http://localhost:${port}/api/health\n`);
});

function shutdown(signal) {
  console.log(`\nReceived ${signal}. Shutting down gracefully.`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 8000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
