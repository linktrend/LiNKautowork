import { loadEnv } from './config/env.js';
import { bootstrapApp } from './app.js';
import { logError, logInfo } from './lib/logger.js';

async function start() {
  try {
    const env = await loadEnv();
    const { app, deps } = await bootstrapApp(env);

    const server = app.listen(env.PORT, () => {
      logInfo('LiNKautowork gateway started', {
        port: env.PORT,
        tenantUuid: env.ACTIVE_TENANT_UUID,
      });
    });

    const shutdown = async (signal: string) => {
      logInfo('shutdown signal received', { signal });
      server.close(async () => {
        await deps.natsPublisher.close();
        logInfo('gateway shutdown complete');
        process.exit(0);
      });
    };

    process.on('SIGINT', () => {
      void shutdown('SIGINT');
    });
    process.on('SIGTERM', () => {
      void shutdown('SIGTERM');
    });
  } catch (error) {
    logError('failed to start gateway', {
      error: error instanceof Error ? error.message : 'unknown',
    });
    process.exit(1);
  }
}

void start();
