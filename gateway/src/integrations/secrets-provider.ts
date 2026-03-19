import { SecretManagerServiceClient } from '@google-cloud/secret-manager';
import type { AppEnv } from '../config/env.js';

export class SecretsProvider {
  private readonly client: SecretManagerServiceClient;

  constructor(private readonly env: AppEnv) {
    this.client = new SecretManagerServiceClient();
  }

  async getSecrets(names: string[]): Promise<Record<string, string>> {
    if (names.length === 0) {
      return {};
    }

    if (!this.env.GCP_PROJECT_ID) {
      throw new Error('GCP_PROJECT_ID is required for JIT secret retrieval');
    }

    const resolved: Record<string, string> = {};
    for (const name of names) {
      const resource = `projects/${this.env.GCP_PROJECT_ID}/secrets/${name}/versions/latest`;
      const [version] = await this.client.accessSecretVersion({ name: resource });
      const value = version.payload?.data?.toString('utf8') ?? '';
      resolved[name] = value;
    }

    return resolved;
  }
}
