import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const repoRoot = join(import.meta.dirname, '../../..');
const bootstrap = readFileSync(join(repoRoot, 'packages/automation-contracts/disposable-db/bootstrap-platform.sql'), 'utf8');
const packageJson = JSON.parse(readFileSync(join(repoRoot, 'docs/contracts/server01/MIGRATION-PACKAGE.json'), 'utf8')) as {
  orderedSql: Array<{ path: string }>;
};
const verificationSql = readFileSync(join(repoRoot, 'docs/contracts/server01/verification.sql'), 'utf8');
const fixtureSql = readFileSync(join(repoRoot, 'docs/contracts/server01/fixtures/server01-conformance.sql'), 'utf8');

function upSql(rel: string): string {
  const text = readFileSync(join(repoRoot, rel), 'utf8');
  const marker = '-- migrate:down';
  const index = text.indexOf(marker);
  return index === -1 ? text : text.slice(0, index);
}

function downSql(rel: string): string {
  const text = readFileSync(join(repoRoot, rel), 'utf8');
  const marker = '-- migrate:down';
  const index = text.indexOf(marker);
  if (index === -1) {
    throw new Error(`missing migrate:down in ${rel}`);
  }
  return text.slice(index + marker.length);
}

const additiveRel = 'supabase/migrations/20260910_000001_lautowork_server01_live_interfaces.sql';

class DisposablePostgres {
  readonly name: string;
  constructor() {
    this.name = `aw01-${process.pid}-${Date.now()}`;
  }

  start(): void {
    execFileSync('docker', [
      'run', '-d', '--rm',
      '--name', this.name,
      '-e', 'POSTGRES_PASSWORD=ltfx.ph.aw01.disposable-postgres.v1',
      '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
      '-e', 'POSTGRES_DB=automation_contracts',
      'postgres:16-alpine',
    ], { stdio: 'pipe' });
    const deadline = Date.now() + 60_000;
    let last = '';
    while (Date.now() < deadline) {
      try {
        last = execFileSync('docker', ['exec', this.name, 'pg_isready', '-U', 'postgres', '-d', 'automation_contracts'], {
          encoding: 'utf8',
        });
        if (last.includes('accepting connections')) {
          return;
        }
      } catch (error) {
        last = error instanceof Error ? error.message : String(error);
      }
      execFileSync('sleep', ['1']);
    }
    throw new Error(`postgres did not become ready: ${last}`);
  }

  sql(script: string): string {
    const dir = mkdtempSync(join(tmpdir(), 'aw01-sql-'));
    const file = join(dir, 'stmt.sql');
    writeFileSync(file, script);
    try {
      return execFileSync('docker', [
        'exec', '-i', this.name,
        'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'automation_contracts', '-q', '-t', '-A',
      ], {
        input: readFileSync(file),
        encoding: 'utf8',
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }

  stop(): void {
    try {
      execFileSync('docker', ['rm', '-f', this.name], { stdio: 'pipe' });
    } catch {
      // already removed
    }
  }
}

function applyPredecessor(db: DisposablePostgres): void {
  db.sql(bootstrap);
  for (const entry of packageJson.orderedSql) {
    if (entry.path === additiveRel) {
      continue;
    }
    db.sql(upSql(entry.path));
  }
}

function applyAdditive(db: DisposablePostgres): void {
  db.sql(upSql(additiveRel));
}

describe('server01 live-interface disposable postgres', () => {
  const db = new DisposablePostgres();

  beforeAll(() => {
    db.start();
    applyPredecessor(db);
    applyAdditive(db);
  }, 180_000);

  afterAll(() => {
    db.stop();
  });

  it('passes role, RLS, fingerprint and least-privilege verification SQL', () => {
    expect(() => db.sql(verificationSql)).not.toThrow();
    const status = db.sql("select lautowork.server01_package_status();").trim();
    expect(status).toBe('complete');
  });

  it('proves idempotent PREPARED accept, org isolation, callback replay and append-only receipts', () => {
    expect(() => db.sql(fixtureSql)).not.toThrow();
    const prepared = db.sql(`
      select state from lautowork.server01_prepared_intents
      where request_id = '00000000-0000-0000-0000-0000000000c1';
    `).trim();
    expect(prepared).toBe('terminal');
    const outboxKinds = db.sql(`
      select string_agg(kind, ',' order by kind)
      from lautowork.server01_intent_outbox
      where request_id = '00000000-0000-0000-0000-0000000000c1';
    `).trim();
    expect(outboxKinds.split(',')).toEqual(expect.arrayContaining(['prepared_intent', 'callback_ack', 'receipt_committed']));
  });

  it('rejects concurrent second jobs for the same idempotency key', () => {
    db.sql(`
      do $$
      declare
        digest text := 'sha256:' || repeat('11', 32);
        request jsonb;
        first jsonb;
        second jsonb;
        n integer;
      begin
        perform set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000a1', false);
        request := jsonb_build_object(
          'request_id', '00000000-0000-0000-0000-0000000000c2',
          'org_id', '00000000-0000-0000-0000-0000000000a1',
          'work_ref', 'program://issues/opaque-work-2',
          'authority_ref', 'platform://authority/opaque-2',
          'actor_id', 'svc-gateway',
          'audience', 'autowork',
          'capability', 'automation.invoke',
          'credential_id', 'credential-1',
          'credential_binding_ref', 'gsm://bindings/gateway-binding-1',
          'binding_id', 'gateway-binding-1',
          'automation_id', 'repo-precheck',
          'automation_version', '1.0.0',
          'definition_digest', digest,
          'configuration_digest', digest,
          'configuration_ref', 'autowork://config/2',
          'allowed_operation', 'precheck',
          'operation_kind', 'precheck',
          'input_ref', 'autowork://input/2',
          'input_digest', digest,
          'idempotency_key', 'idempotency-key-02',
          'callback_binding_ref', 'autowork://callback/2',
          'budget_ceiling_ref', 'autowork://budget/2',
          'expires_at', '2030-01-01T00:00:00Z'
        );
        first := lautowork.server01_accept_invocation(request, digest);
        second := lautowork.server01_accept_invocation(request, digest);
        if (first->>'replay')::boolean then raise exception 'first accept unexpectedly replayed'; end if;
        if not (second->>'replay')::boolean then raise exception 'identical second accept was not replayed'; end if;
        select count(*) into n from lautowork.server01_invocation_requests where idempotency_key = 'idempotency-key-02';
        if n <> 1 then raise exception 'expected one invocation row, got %', n; end if;
      end $$;
    `);
  });

  it('reports partial apply and fingerprint drift as stop conditions', () => {
    const before = db.sql('select lautowork.server01_live_fingerprint();').trim();
    db.sql("update lautowork.server01_package_control set live_fingerprint = 'sha256:' || repeat('00', 32);");
    expect(db.sql('select lautowork.server01_package_status();').trim()).toBe('drift');
    db.sql(`update lautowork.server01_package_control set live_fingerprint = '${before}';`);
    expect(db.sql('select lautowork.server01_package_status();').trim()).toBe('complete');
    db.sql("update lautowork.server01_package_control set apply_state = 'started', completed_at = null;");
    expect(db.sql('select lautowork.server01_package_status();').trim()).toBe('partial');
    db.sql(`update lautowork.server01_package_control set apply_state = 'complete', live_fingerprint = '${before}', completed_at = now();`);
    expect(db.sql('select lautowork.server01_package_status();').trim()).toBe('complete');
  });

  it('rolls back the additive migration on a disposable database only', () => {
    db.sql(downSql(additiveRel));
    const gone = db.sql(`
      select count(*) from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'lautowork' and c.relname like 'server01_%';
    `).trim();
    expect(gone).toBe('0');
    const roleGone = db.sql("select count(*) from pg_roles where rolname = 'svc_lautowork_gateway';").trim();
    expect(roleGone).toBe('0');
  });
});

describe('server01 fresh install versus upgrade', () => {
  it('fresh-installs the full ordered package onto a new disposable database', () => {
    const fresh = new DisposablePostgres();
    fresh.start();
    try {
      fresh.sql(bootstrap);
      for (const entry of packageJson.orderedSql) {
        fresh.sql(upSql(entry.path));
      }
      fresh.sql(verificationSql);
      expect(fresh.sql('select lautowork.server01_package_status();').trim()).toBe('complete');
    } finally {
      fresh.stop();
    }
  }, 180_000);
});
