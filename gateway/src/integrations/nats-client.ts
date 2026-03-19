import { connect, type NatsConnection, StringCodec } from 'nats';
import type { AppEnv } from '../config/env.js';
import { logError, logInfo, logWarn } from '../lib/logger.js';

export class NatsPublisher {
  private connection: NatsConnection | null = null;
  private readonly codec = StringCodec();

  constructor(private readonly env: AppEnv) {}

  async connect(): Promise<void> {
    try {
      this.connection = await connect({ servers: this.env.NATS_URL });
      logInfo('connected to NATS', { servers: this.env.NATS_URL });
    } catch (error) {
      logWarn('failed to connect to NATS, continuing in degraded mode', {
        error: error instanceof Error ? error.message : 'unknown',
      });
      this.connection = null;
    }
  }

  async publish(subject: string, payload: Record<string, unknown>): Promise<void> {
    if (!this.connection) {
      throw new Error('NATS connection unavailable');
    }

    this.connection.publish(subject, this.codec.encode(JSON.stringify(payload)));
  }

  async close(): Promise<void> {
    if (!this.connection) return;
    try {
      await this.connection.drain();
      this.connection.close();
      this.connection = null;
    } catch (error) {
      logError('failed to close NATS connection', {
        error: error instanceof Error ? error.message : 'unknown',
      });
    }
  }
}
