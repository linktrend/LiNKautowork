import { z } from 'zod';
import { SecretManagerServiceClient } from '@google-cloud/secret-manager';
import { CANONICAL_INTERNAL_TENANT_UUID, INTERNAL_TENANT_SLUG } from '../constants/tenant.js';

const envSchema = z.object({
  NODE_ENV: z.string().default('development'),
  PORT: z.coerce.number().default(8080),
  REPLAY_WINDOW_SECONDS: z.coerce.number().default(300),
  LINK_HMAC_SHARED_SECRETS: z.string().optional(),
  LINK_HMAC_SHARED_SECRETS_SECRET_NAME: z.string().default('LINKAUTOWORK_LINK_HMAC_SHARED_SECRETS'),
  LINK_SERVICE_TOKENS: z.string().optional(),
  LINK_SERVICE_TOKENS_SECRET_NAME: z.string().default('LINKAUTOWORK_LINK_SERVICE_TOKENS'),
  LINK_CONTROL_TOKEN: z.string().optional(),
  LINK_CONTROL_TOKEN_SECRET_NAME: z.string().default('LINKAUTOWORK_LINK_CONTROL_TOKEN'),

  ACTIVE_TENANT_UUID: z.string().uuid().default(CANONICAL_INTERNAL_TENANT_UUID),
  ACTIVE_TENANT_SLUG: z.string().default(INTERNAL_TENANT_SLUG),

  SUPABASE_URL: z.string().url(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(1).optional(),
  SUPABASE_SERVICE_ROLE_KEY_SECRET_NAME: z
    .string()
    .default('LINKAUTOWORK_SUPABASE_SERVICE_ROLE_KEY'),
  SUPABASE_AUDIT_RPC: z.string().default('linkautowork_write_audit_run'),

  N8N_BASE_URL: z.string().url(),
  N8N_WEBHOOK_PATH_PREFIX: z.string().default('/webhook'),
  N8N_API_BASE_PATH: z.string().default('/api/v1'),
  N8N_API_KEY: z.string().min(1).optional(),
  N8N_API_KEY_SECRET_NAME: z.string().default('LINKAUTOWORK_N8N_API_KEY'),

  NATS_URL: z.string().default('nats://nats:4222'),
  ENABLE_INTERNAL_MIRROR_SUBJECTS: z.string().default('true'),

  GCP_PROJECT_ID: z.string().optional(),
  GOOGLE_CLOUD_PROJECT: z.string().optional(),
  GOOGLE_APPLICATION_CREDENTIALS: z.string().optional(),

  SLACK_SIGNING_SECRET: z.string().optional(),
  SLACK_SIGNING_SECRET_SECRET_NAME: z.string().default('LINKAUTOWORK_SLACK_SIGNING_SECRET'),
});

function parseKeyValuePairs(raw: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const pair of raw.split(',')) {
    const [key, ...rest] = pair.split(':');
    if (!key || rest.length === 0) continue;
    map.set(key.trim(), rest.join(':').trim());
  }
  return map;
}

export type AppEnv = Omit<
  z.infer<typeof envSchema>,
  | 'LINK_HMAC_SHARED_SECRETS'
  | 'LINK_SERVICE_TOKENS'
  | 'LINK_CONTROL_TOKEN'
  | 'SUPABASE_SERVICE_ROLE_KEY'
  | 'N8N_API_KEY'
> & {
  LINK_HMAC_SHARED_SECRETS: string;
  LINK_SERVICE_TOKENS: string;
  LINK_CONTROL_TOKEN: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  N8N_API_KEY: string;
  hmacSecrets: Map<string, string>;
  serviceTokens: Map<string, string>;
  enableInternalMirrorSubjects: boolean;
};

export async function loadEnv(
  overrides: Partial<Record<string, string | undefined>> = {}
): Promise<AppEnv> {
  const parsed = envSchema.parse({
    ...process.env,
    ...overrides,
  });

  const gcpProjectId = parsed.GCP_PROJECT_ID ?? parsed.GOOGLE_CLOUD_PROJECT;

  const [
    linkHmacSharedSecrets,
    linkServiceTokens,
    linkControlToken,
    supabaseServiceRoleKey,
    n8nApiKey,
    slackSigningSecret,
  ] = await Promise.all([
    resolveRequiredSecret({
      directValue: parsed.LINK_HMAC_SHARED_SECRETS,
      secretName: parsed.LINK_HMAC_SHARED_SECRETS_SECRET_NAME,
      projectId: gcpProjectId,
      label: 'LINK_HMAC_SHARED_SECRETS',
    }),
    resolveRequiredSecret({
      directValue: parsed.LINK_SERVICE_TOKENS,
      secretName: parsed.LINK_SERVICE_TOKENS_SECRET_NAME,
      projectId: gcpProjectId,
      label: 'LINK_SERVICE_TOKENS',
    }),
    resolveRequiredSecret({
      directValue: parsed.LINK_CONTROL_TOKEN,
      secretName: parsed.LINK_CONTROL_TOKEN_SECRET_NAME,
      projectId: gcpProjectId,
      label: 'LINK_CONTROL_TOKEN',
    }),
    resolveRequiredSecret({
      directValue: parsed.SUPABASE_SERVICE_ROLE_KEY,
      secretName: parsed.SUPABASE_SERVICE_ROLE_KEY_SECRET_NAME,
      projectId: gcpProjectId,
      label: 'SUPABASE_SERVICE_ROLE_KEY',
    }),
    resolveRequiredSecret({
      directValue: parsed.N8N_API_KEY,
      secretName: parsed.N8N_API_KEY_SECRET_NAME,
      projectId: gcpProjectId,
      label: 'N8N_API_KEY',
    }),
    resolveOptionalSecret({
      directValue: parsed.SLACK_SIGNING_SECRET,
      secretName: parsed.SLACK_SIGNING_SECRET_SECRET_NAME,
      projectId: gcpProjectId,
    }),
  ]);

  return {
    ...parsed,
    GCP_PROJECT_ID: gcpProjectId,
    LINK_HMAC_SHARED_SECRETS: linkHmacSharedSecrets,
    LINK_SERVICE_TOKENS: linkServiceTokens,
    LINK_CONTROL_TOKEN: linkControlToken,
    SUPABASE_SERVICE_ROLE_KEY: supabaseServiceRoleKey,
    N8N_API_KEY: n8nApiKey,
    SLACK_SIGNING_SECRET: slackSigningSecret,
    hmacSecrets: parseKeyValuePairs(linkHmacSharedSecrets),
    serviceTokens: parseKeyValuePairs(linkServiceTokens),
    enableInternalMirrorSubjects: parsed.ENABLE_INTERNAL_MIRROR_SUBJECTS === 'true',
  };
}

async function resolveRequiredSecret(args: {
  directValue?: string;
  secretName: string;
  projectId?: string;
  label: string;
}): Promise<string> {
  if (args.directValue && args.directValue.trim()) {
    return args.directValue.trim();
  }

  if (!args.secretName.trim()) {
    throw new Error(`${args.label} requires a non-empty secret name`);
  }

  return resolveFromGsm(args.secretName, args.projectId, args.label);
}

async function resolveOptionalSecret(args: {
  directValue?: string;
  secretName: string;
  projectId?: string;
}): Promise<string | undefined> {
  if (args.directValue && args.directValue.trim()) {
    return args.directValue.trim();
  }
  if (!args.secretName.trim()) {
    return undefined;
  }
  try {
    return await resolveFromGsm(args.secretName, args.projectId, args.secretName);
  } catch {
    return undefined;
  }
}

async function resolveFromGsm(secretName: string, projectId: string | undefined, label: string): Promise<string> {
  if (!projectId) {
    throw new Error(`${label} requires GCP project configuration for GSM resolution`);
  }

  const client = new SecretManagerServiceClient();
  const resource = `projects/${projectId}/secrets/${secretName}/versions/latest`;
  const [version] = await client.accessSecretVersion({ name: resource });
  const value = version.payload?.data?.toString('utf8')?.trim() ?? '';
  if (!value) {
    throw new Error(`${label} resolved empty value from GSM secret ${secretName}`);
  }
  return value;
}
