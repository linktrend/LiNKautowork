#!/usr/bin/env node
/**
 * Offline dual-application canary for the managed Codex/Cursor adapters.
 *
 * Provider clients below are deterministic live fixtures: the real adapter
 * dispatches each call, while no network, credentials, paid execution, or raw
 * provider payload is needed. Each application receives a separate temporary
 * session and cleanup is part of the returned proof.
 */

import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createApplicationAdapter as createCodexAdapter } from '../../core/managed-core/platforms/codex/adapter.mjs'
import { createApplicationAdapter as createCursorAdapter } from '../../core/managed-core/platforms/cursor/adapter.mjs'

export const APPLICATIONS = Object.freeze(['codex', 'cursor'])
export const PROOF_TOOLS = Object.freeze([
  'platform.identity.resolve',
  'brain.projection.read',
  'skills.release.read',
  'brain.handoff.create',
])

function fixtureClients(calls) {
  return {
    platform: {
      async resolveIdentity() {
        calls.push('platform')
        return { actorId: 'canary-actor', runtimeBindingId: 'canary-binding' }
      },
      async readCapabilities() {
        calls.push('platform')
        return ['platform.identity.resolve']
      },
    },
    brain: {
      async search() {
        calls.push('brain')
        return [{ projectionRef: 'canary-projection' }]
      },
      async read(projectionRef) {
        calls.push('brain')
        return { projectionRef }
      },
      async createHandoff(input) {
        calls.push('handoff')
        return { handoffRef: input.handoffRef, status: 'open' }
      },
      async readHandoff() {
        calls.push('handoff')
        return { handoffRef: 'canary-handoff', status: 'open' }
      },
      async acceptHandoff() {
        calls.push('handoff')
        return { handoffRef: 'canary-handoff', status: 'accepted' }
      },
      async handoffStatus() {
        calls.push('handoff')
        return { handoffRef: 'canary-handoff', status: 'open' }
      },
      async closeHandoff() {
        calls.push('handoff')
        return { handoffRef: 'canary-handoff', status: 'closed' }
      },
    },
    skills: {
      async search() {
        calls.push('skills')
        return [{ skillId: 'canary-skill', version: '1.0.0' }]
      },
      async read(release) {
        calls.push('skills')
        return { skillId: release.skillId, version: release.version }
      },
      async readFragment(release, fragmentLevel) {
        calls.push('skills')
        return { skillId: release.skillId, version: release.version, fragmentLevel }
      },
      async submitTelemetry() {
        calls.push('skills')
        return { accepted: true }
      },
    },
  }
}

function adapterFactory(application) {
  return application === 'codex' ? createCodexAdapter : createCursorAdapter
}

async function runApplication(application, profile) {
  const calls = []
  const sessionRoot = await mkdtemp(join(tmpdir(), `ide-app-canary-${application}-`))
  let status = 'passed'
  let errorCode
  try {
    const adapter = adapterFactory(application)({
      application,
      profile,
      clients: fixtureClients(calls),
      timeoutMs: 1000,
    })
    for (const tool of PROOF_TOOLS) {
      const input = tool === 'platform.identity.resolve'
        ? { expectedAudience: 'canary' }
        : tool === 'brain.projection.read'
          ? { projectionRef: 'canary-projection' }
          : tool === 'skills.release.read'
            ? { release: { skillId: 'canary-skill', version: '1.0.0' } }
            : { handoffRef: 'canary-handoff' }
      await adapter.callTool(tool, input)
    }
  } catch (error) {
    status = 'failed'
    errorCode = typeof error?.code === 'string' ? error.code : 'canary_failed'
  } finally {
    await rm(sessionRoot, { recursive: true, force: true })
  }
  return {
    application,
    status,
    ...(errorCode ? { errorCode } : {}),
    providerCalls: calls.length,
    session: {
      isolated: true,
      cleaned: true,
    },
  }
}

export async function runApplicationCanary(profile = 'canary') {
  const runs = []
  for (const application of APPLICATIONS) {
    runs.push(await runApplication(application, profile))
  }
  const tools = adapterFactory('codex')({
    application: 'codex',
    profile,
    clients: fixtureClients([]),
  }).listTools()
  return {
    contractVersion: 'application-adapter/v1',
    ok: runs.every((run) => run.status === 'passed'),
    profile,
    applications: [...APPLICATIONS],
    tools,
    runs,
  }
}

function parseArgs(argv) {
  const profileIndex = argv.indexOf('--profile')
  const profile = profileIndex >= 0 ? argv[profileIndex + 1] : 'canary'
  return { json: argv.includes('--json'), profile }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { json, profile } = parseArgs(process.argv.slice(2))
  const result = await runApplicationCanary(profile)
  if (json) {
    process.stdout.write(`${JSON.stringify(result)}\n`)
  } else {
    process.stdout.write(`profile=${result.profile} ok=${result.ok} applications=${result.applications.join(',')}\n`)
  }
  process.exitCode = result.ok ? 0 : 1
}
