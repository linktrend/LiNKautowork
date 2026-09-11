import { execFileSync, spawn } from 'node:child_process';
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
const configuredDatabase = 'automation_contracts';

function pgIsReadyAccepting(containerName: string): string | null {
  try {
    const output = execFileSync('docker', [
      'exec', containerName, 'pg_isready', '-U', 'postgres', '-d', configuredDatabase,
    ], {
      encoding: 'utf8',
    });
    return output.includes('accepting connections') ? output : null;
  } catch {
    return null;
  }
}

function configuredDatabaseIsQueryable(containerName: string): boolean {
  try {
    execFileSync('docker', [
      'exec', containerName,
      'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', configuredDatabase,
      '-c', 'select 1',
    ], { stdio: 'pipe' });
    return true;
  } catch {
    return false;
  }
}

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
      '-e', `POSTGRES_DB=${configuredDatabase}`,
      'postgres:16-alpine',
    ], { stdio: 'pipe' });
    const deadline = Date.now() + 60_000;
    let last = 'postgres did not become queryable';
    while (Date.now() < deadline) {
      if (configuredDatabaseIsQueryable(this.name)) {
        return;
      }
      const ready = pgIsReadyAccepting(this.name);
      last = ready
        ? `${ready.trim()} but ${configuredDatabase} is not yet queryable`
        : last;
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
        'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', configuredDatabase, '-q', '-t', '-A',
      ], {
        input: readFileSync(file),
        encoding: 'utf8',
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }

  sqlAsync(script: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = spawn('docker', [
        'exec', '-i', this.name,
        'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', configuredDatabase, '-q', '-t', '-A',
      ]);
      let stdout = '';
      let stderr = '';
      child.stdout.setEncoding('utf8');
      child.stderr.setEncoding('utf8');
      child.stdout.on('data', (chunk: string) => {
        stdout += chunk;
      });
      child.stderr.on('data', (chunk: string) => {
        stderr += chunk;
      });
      child.on('error', reject);
      child.on('close', (code) => {
        if (code === 0) {
          resolve(stdout);
          return;
        }
        reject(new Error(stderr || `psql exited ${code}`));
      });
      child.stdin.end(script);
    });
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

describe('server01 disposable postgres readiness', () => {
  it('proves pg_isready can accept connections before automation_contracts is queryable', () => {
    const name = `aw01-ready-${process.pid}-${Date.now()}`;
    execFileSync('docker', [
      'run', '-d', '--rm',
      '--name', name,
      '-e', 'POSTGRES_PASSWORD=ltfx.ph.aw01.disposable-postgres.v1',
      '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
      'postgres:16-alpine',
    ], { stdio: 'pipe' });
    try {
      const deadline = Date.now() + 60_000;
      let accepting: string | null = null;
      while (Date.now() < deadline) {
        accepting = pgIsReadyAccepting(name);
        if (accepting) {
          break;
        }
        execFileSync('sleep', ['1']);
      }
      expect(accepting).toContain('accepting connections');
      expect(configuredDatabaseIsQueryable(name)).toBe(false);
    } finally {
      try {
        execFileSync('docker', ['rm', '-f', name], { stdio: 'pipe' });
      } catch {
        // already removed
      }
    }
  }, 180_000);
});

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

  it('serializes identical concurrent accepts across two sessions into one fresh and one replay', async () => {
    const digest = `sha256:${'33'.repeat(32)}`;
    const acceptSql = `
      select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000a1', false);
      select lautowork.server01_accept_invocation(
        jsonb_build_object(
          'request_id', '00000000-0000-0000-0000-0000000000c5',
          'org_id', '00000000-0000-0000-0000-0000000000a1',
          'work_ref', 'program://issues/opaque-work-5',
          'authority_ref', 'platform://authority/opaque-5',
          'actor_id', 'svc-gateway',
          'audience', 'autowork',
          'capability', 'automation.invoke',
          'credential_id', 'credential-1',
          'credential_binding_ref', 'gsm://bindings/gateway-binding-1',
          'binding_id', 'gateway-binding-1',
          'automation_id', 'repo-precheck',
          'automation_version', '1.0.0',
          'definition_digest', '${digest}',
          'configuration_digest', '${digest}',
          'configuration_ref', 'autowork://config/5',
          'allowed_operation', 'precheck',
          'operation_kind', 'precheck',
          'input_ref', 'autowork://input/5',
          'input_digest', '${digest}',
          'idempotency_key', 'idempotency-key-05',
          'callback_binding_ref', 'autowork://callback/5',
          'budget_ceiling_ref', 'autowork://budget/5',
          'expires_at', '2030-01-01T00:00:00Z'
        ),
        '${digest}'
      );
    `;
    const [first, second] = await Promise.all([db.sqlAsync(acceptSql), db.sqlAsync(acceptSql)]);
    const replays = [first, second]
      .map((output) => JSON.parse(output.trim().split('\n').at(-1) ?? '{}') as { replay: boolean })
      .map((row) => row.replay)
      .sort();
    expect(replays).toEqual([false, true]);
    expect(db.sql(`
      select count(*) from lautowork.server01_invocation_requests where idempotency_key = 'idempotency-key-05';
    `).trim()).toBe('1');
  }, 60_000);

  it('keeps concurrent different-fingerprint accepts as an explicit idempotency conflict', async () => {
    const digestA = `sha256:${'44'.repeat(32)}`;
    const digestB = `sha256:${'45'.repeat(32)}`;
    const accept = (requestId: string, digest: string) => `
      select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000a1', false);
      select lautowork.server01_accept_invocation(
        jsonb_build_object(
          'request_id', '${requestId}',
          'org_id', '00000000-0000-0000-0000-0000000000a1',
          'work_ref', 'program://issues/opaque-work-6',
          'authority_ref', 'platform://authority/opaque-6',
          'actor_id', 'svc-gateway',
          'audience', 'autowork',
          'capability', 'automation.invoke',
          'credential_id', 'credential-1',
          'credential_binding_ref', 'gsm://bindings/gateway-binding-1',
          'binding_id', 'gateway-binding-1',
          'automation_id', 'repo-precheck',
          'automation_version', '1.0.0',
          'definition_digest', '${digest}',
          'configuration_digest', '${digest}',
          'configuration_ref', 'autowork://config/6',
          'allowed_operation', 'precheck',
          'operation_kind', 'precheck',
          'input_ref', 'autowork://input/6',
          'input_digest', '${digest}',
          'idempotency_key', 'idempotency-key-06',
          'callback_binding_ref', 'autowork://callback/6',
          'budget_ceiling_ref', 'autowork://budget/6',
          'expires_at', '2030-01-01T00:00:00Z'
        ),
        '${digest}'
      );
    `;
    const results = await Promise.allSettled([
      db.sqlAsync(accept('00000000-0000-0000-0000-0000000000c6', digestA)),
      db.sqlAsync(accept('00000000-0000-0000-0000-0000000000c7', digestB)),
    ]);
    const fulfilled = results.filter((row) => row.status === 'fulfilled');
    const rejected = results.filter((row) => row.status === 'rejected');
    expect(fulfilled).toHaveLength(1);
    expect(rejected).toHaveLength(1);
    const err = rejected[0] as PromiseRejectedResult;
    expect(String(err.reason)).toMatch(/server01 idempotency conflict|23505/);
    expect(db.sql(`
      select count(*) from lautowork.server01_invocation_requests where idempotency_key = 'idempotency-key-06';
    `).trim()).toBe('1');
  }, 60_000);

  it('rejects mismatched callback request ids before any receipt, callback, or outbox write', () => {
    db.sql(`
      do $$
      declare
        digest text := 'sha256:' || repeat('55', 32);
        request_a jsonb;
        request_b jsonb;
        receipts_before integer;
        callbacks_before integer;
        outbox_before integer;
        receipts_after integer;
        callbacks_after integer;
        outbox_after integer;
        admitted jsonb;
      begin
        perform set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000a1', false);
        request_a := jsonb_build_object(
          'request_id', '00000000-0000-0000-0000-0000000000c3',
          'org_id', '00000000-0000-0000-0000-0000000000a1',
          'work_ref', 'program://issues/opaque-work-3',
          'authority_ref', 'platform://authority/opaque-3',
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
          'configuration_ref', 'autowork://config/3',
          'allowed_operation', 'precheck',
          'operation_kind', 'precheck',
          'input_ref', 'autowork://input/3',
          'input_digest', digest,
          'idempotency_key', 'idempotency-key-03',
          'callback_binding_ref', 'autowork://callback/3',
          'budget_ceiling_ref', 'autowork://budget/3',
          'expires_at', '2030-01-01T00:00:00Z'
        );
        request_b := request_a || jsonb_build_object(
          'request_id', '00000000-0000-0000-0000-0000000000c4',
          'work_ref', 'program://issues/opaque-work-4',
          'idempotency_key', 'idempotency-key-04',
          'input_ref', 'autowork://input/4',
          'callback_binding_ref', 'autowork://callback/4'
        );
        perform lautowork.server01_accept_invocation(request_a, digest);
        perform lautowork.server01_accept_invocation(request_b, digest);
        select count(*) into receipts_before from lautowork.server01_receipts
          where request_id in ('00000000-0000-0000-0000-0000000000c3', '00000000-0000-0000-0000-0000000000c4');
        select count(*) into callbacks_before from lautowork.server01_callbacks
          where request_id in ('00000000-0000-0000-0000-0000000000c3', '00000000-0000-0000-0000-0000000000c4');
        select count(*) into outbox_before from lautowork.server01_intent_outbox
          where request_id in ('00000000-0000-0000-0000-0000000000c3', '00000000-0000-0000-0000-0000000000c4')
            and kind in ('callback_ack', 'receipt_committed');
        begin
          perform lautowork.server01_admit_callback(jsonb_build_object(
            'request_id', '00000000-0000-0000-0000-0000000000c3',
            'org_id', '00000000-0000-0000-0000-0000000000a1',
            'callback_binding_ref', 'autowork://callback/3',
            'callback_fingerprint', digest,
            'source_timestamp', '2030-01-01T00:00:01Z',
            'receipt', jsonb_build_object(
              'receipt_id', '00000000-0000-0000-0000-0000000000d3',
              'request_id', '00000000-0000-0000-0000-0000000000c4',
              'state', 'succeeded',
              'request_fingerprint', digest,
              'evidence_ref', 'autowork://evidence/3',
              'result_ref', 'autowork://result/3'
            )
          ));
          raise exception 'mismatched callback request ids unexpectedly admitted';
        exception when others then
          if sqlerrm not like '%callback request mismatch%' then raise; end if;
        end;
        select count(*) into receipts_after from lautowork.server01_receipts
          where request_id in ('00000000-0000-0000-0000-0000000000c3', '00000000-0000-0000-0000-0000000000c4');
        select count(*) into callbacks_after from lautowork.server01_callbacks
          where request_id in ('00000000-0000-0000-0000-0000000000c3', '00000000-0000-0000-0000-0000000000c4');
        select count(*) into outbox_after from lautowork.server01_intent_outbox
          where request_id in ('00000000-0000-0000-0000-0000000000c3', '00000000-0000-0000-0000-0000000000c4')
            and kind in ('callback_ack', 'receipt_committed');
        if receipts_before <> 0 or callbacks_before <> 0 or outbox_before <> 0 then
          raise exception 'expected empty callback side effects before mismatch';
        end if;
        if receipts_after <> receipts_before or callbacks_after <> callbacks_before or outbox_after <> outbox_before then
          raise exception 'mismatched callback persisted partial writes';
        end if;
        admitted := lautowork.server01_admit_callback(jsonb_build_object(
          'request_id', '00000000-0000-0000-0000-0000000000c3',
          'org_id', '00000000-0000-0000-0000-0000000000a1',
          'callback_binding_ref', 'autowork://callback/3',
          'callback_fingerprint', digest,
          'source_timestamp', '2030-01-01T00:00:01Z',
          'receipt', jsonb_build_object(
            'receipt_id', '00000000-0000-0000-0000-0000000000d3',
            'request_id', '00000000-0000-0000-0000-0000000000c3',
            'state', 'succeeded',
            'request_fingerprint', digest,
            'evidence_ref', 'autowork://evidence/3',
            'result_ref', 'autowork://result/3'
          )
        ));
        if (admitted->>'replay')::boolean then raise exception 'valid callback unexpectedly replayed'; end if;
        if not (lautowork.server01_admit_callback(jsonb_build_object(
            'request_id', '00000000-0000-0000-0000-0000000000c3',
            'org_id', '00000000-0000-0000-0000-0000000000a1',
            'callback_binding_ref', 'autowork://callback/3',
            'callback_fingerprint', digest,
            'source_timestamp', '2030-01-01T00:00:01Z',
            'receipt', jsonb_build_object(
              'receipt_id', '00000000-0000-0000-0000-0000000000d3',
              'request_id', '00000000-0000-0000-0000-0000000000c3',
              'state', 'succeeded',
              'request_fingerprint', digest,
              'evidence_ref', 'autowork://evidence/3',
              'result_ref', 'autowork://result/3'
            )
          ))->>'replay')::boolean then
          raise exception 'valid callback replay was not detected';
        end if;
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

  it('impersonates every EXECUTE grantee and matches owner fingerprint and package status', () => {
    const output = db.sql(`
      do $$
      declare
        v_fp text := lautowork.server01_live_fingerprint();
        v_status text := lautowork.server01_package_status();
        r name;
        seen integer := 0;
      begin
        if v_status is distinct from 'complete' then
          raise exception 'owner package status is %, expected complete', v_status;
        end if;
        for r in
          select fp.rolname
            from (
              select distinct pg_get_userbyid(ae.grantee) as rolname
                from pg_proc p
                join pg_namespace n on n.oid = p.pronamespace
                cross join lateral aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) as ae
               where n.nspname = 'lautowork'
                 and p.proname = 'server01_live_fingerprint'
                 and pg_get_function_identity_arguments(p.oid) = ''
                 and ae.privilege_type = 'EXECUTE'
                 and ae.grantee <> 0
            ) fp
            join (
              select distinct pg_get_userbyid(ae.grantee) as rolname
                from pg_proc p
                join pg_namespace n on n.oid = p.pronamespace
                cross join lateral aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) as ae
               where n.nspname = 'lautowork'
                 and p.proname = 'server01_package_status'
                 and pg_get_function_identity_arguments(p.oid) = ''
                 and ae.privilege_type = 'EXECUTE'
                 and ae.grantee <> 0
            ) st on st.rolname = fp.rolname
           order by 1
        loop
          seen := seen + 1;
          execute format('set local role %I', r);
          if lautowork.server01_live_fingerprint() is distinct from v_fp then
            raise exception 'fingerprint drifted for role %', r;
          end if;
          if lautowork.server01_package_status() is distinct from v_status then
            raise exception 'package status drifted for role %', r;
          end if;
          execute 'reset role';
        end loop;
        if seen = 0 then
          raise exception 'no EXECUTE grantees found for both fingerprint and package status';
        end if;
      end $$;
      select count(*) from (
        select fp.rolname
          from (
            select distinct pg_get_userbyid(ae.grantee) as rolname
              from pg_proc p
              join pg_namespace n on n.oid = p.pronamespace
              cross join lateral aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) as ae
             where n.nspname = 'lautowork'
               and p.proname = 'server01_live_fingerprint'
               and pg_get_function_identity_arguments(p.oid) = ''
               and ae.privilege_type = 'EXECUTE'
               and ae.grantee <> 0
          ) fp
          join (
            select distinct pg_get_userbyid(ae.grantee) as rolname
              from pg_proc p
              join pg_namespace n on n.oid = p.pronamespace
              cross join lateral aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) as ae
             where n.nspname = 'lautowork'
               and p.proname = 'server01_package_status'
               and pg_get_function_identity_arguments(p.oid) = ''
               and ae.privilege_type = 'EXECUTE'
               and ae.grantee <> 0
          ) st on st.rolname = fp.rolname
      ) grantees;
    `).trim().split('\n').at(-1);
    expect(Number(output)).toBeGreaterThan(0);
  });

  it('rejects missing or incorrect package status for execute grantees', () => {
    const before = db.sql('select lautowork.server01_live_fingerprint();').trim();
    const missing = db.sql(`
      do $$
      declare
        r name := 'svc_lautowork_gateway';
        observed text;
      begin
        delete from lautowork.server01_package_control
         where package_id = 'lautowork.server01.migration-identity/1.0.0';
        execute format('set local role %I', r);
        observed := lautowork.server01_package_status();
        execute 'reset role';
        if observed is distinct from 'absent' then
          raise exception 'missing control row returned %, expected absent', observed;
        end if;
        begin
          perform lautowork.server01_assert_package_ready();
          raise exception 'missing package status was not rejected';
        exception when others then
          if sqlerrm not like '%server01 migration package is not complete%' then raise; end if;
        end;
      end $$;
      select lautowork.server01_package_status();
    `).trim().split('\n').at(-1);
    expect(missing).toBe('absent');
    db.sql(`
      insert into lautowork.server01_package_control
        (package_id, apply_state, expected_relation_count, live_fingerprint, completed_at)
      values (
        'lautowork.server01.migration-identity/1.0.0',
        'complete',
        7,
        '${before}',
        now()
      );
    `);
    const incorrect = db.sql(`
      do $$
      declare
        r name := 'svc_lautowork_runtime';
        observed text;
      begin
        update lautowork.server01_package_control
           set apply_state = 'started', completed_at = null
         where package_id = 'lautowork.server01.migration-identity/1.0.0';
        execute format('set local role %I', r);
        observed := lautowork.server01_package_status();
        execute 'reset role';
        if observed is distinct from 'partial' then
          raise exception 'incorrect apply_state returned %, expected partial', observed;
        end if;
        begin
          perform lautowork.server01_assert_package_ready();
          raise exception 'incorrect package status was not rejected';
        exception when others then
          if sqlerrm not like '%server01 migration package is not complete%' then raise; end if;
        end;
      end $$;
      select lautowork.server01_package_status();
    `).trim().split('\n').at(-1);
    expect(incorrect).toBe('partial');
    db.sql(`
      update lautowork.server01_package_control
         set apply_state = 'complete',
             live_fingerprint = '${before}',
             completed_at = now()
       where package_id = 'lautowork.server01.migration-identity/1.0.0';
    `);
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
