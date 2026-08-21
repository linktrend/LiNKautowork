/**
 * Bounded provider operation clients.
 *
 * These adapters compose the existing fail-closed validators with the shared
 * authenticated transport. They return only validated projections and never
 * expose provider bodies or execution authority.
 */

import { validateProviderRuntimeConfig } from './config.mjs'
import { ProviderTransportError, createTransports } from './transport.mjs'
import { validateAutoworkHandoff, validateAutoworkReceipt, validateAutoworkRequest, validateAutoworkStatus } from './autowork.mjs'
import { validateBrainHandoff, validateBrainProjection } from './brain.mjs'
import { validateLibraryReference } from './libraries.mjs'
import { validatePlatformIdentity } from './platform.mjs'
import { validateSkillsRelease, validateSkillsTelemetry } from './skills.mjs'

const MISSING_TRANSPORT = Object.freeze({
  async request() {
    throw new ProviderTransportError('provider_unavailable', 'provider transport is unavailable', {
      classification: 'unavailable',
    })
  },
})

function transportFor(transports, provider) {
  return transports?.[provider] ?? MISSING_TRANSPORT
}

function boundedList(value, field) {
  if (!Array.isArray(value) || value.length > 32) {
    throw new ProviderTransportError('provider_malformed', `provider response ${field} is malformed`, {
      classification: 'fail_closed',
      provider: field,
    })
  }
  return value
}

function responseBody(value, field) {
  if (value && typeof value === 'object' && !Array.isArray(value) && Object.hasOwn(value, field)) return value[field]
  return value
}

function nowIso(now) {
  return new Date(now ?? Date.now()).toISOString()
}

function pathRef(prefix, ref) {
  if (typeof ref !== 'string' || ref.length === 0 || ref.length > 256) {
    throw new ProviderTransportError('request_reference_invalid', 'provider reference is malformed', {
      classification: 'fail_closed',
    })
  }
  return `${prefix}${encodeURIComponent(ref)}`
}

function tampered(message, provider) {
  throw new ProviderTransportError('provider_tampered', message, {
    classification: 'tamper',
    provider,
  })
}

function holdAutowork(error) {
  if (error instanceof ProviderTransportError && ['provider_unavailable', 'provider_timeout', 'transport_unavailable'].includes(error.code)) {
    return Object.freeze({
      state: 'HOLD',
      provider: 'autowork',
      reason: 'live_runtime_unavailable',
      executionAuthority: 'none',
    })
  }
  throw error
}

function platformClient(transport, now) {
  const client = {
    async resolveIdentity(context = {}) {
      const acceptedContext = { ...context, now: context.now ?? nowIso(now) }
      const body = await transport.request('platform.identity.resolve', { path: '/v1/identity' })
      const claim = responseBody(body, 'claim')
      return validatePlatformIdentity(claim, acceptedContext)
    },
    async readCapabilities() {
      const body = await transport.request('platform.capabilities.read', { path: '/v1/capabilities' })
      const capabilities = responseBody(body, 'capabilities')
      if (!Array.isArray(capabilities) || capabilities.length > 32 || !capabilities.every((item) => typeof item === 'string' && item.length > 0 && item.length < 128)) {
        throw new ProviderTransportError('provider_malformed', 'Platform capabilities response is malformed', {
          classification: 'fail_closed',
          provider: 'platform',
        })
      }
      return Object.freeze([...capabilities])
    },
  }
  client.getIdentity = client.resolveIdentity
  client.getCapabilities = client.readCapabilities
  return Object.freeze(client)
}

function brainClient(transport) {
  async function handoff(operation, request) {
    const body = await transport.request(operation, request)
    const accepted = validateBrainHandoff(responseBody(body, 'handoff'))
    if (request.handoffRef && accepted.handoffRef !== request.handoffRef) tampered('Brain returned a different handoff', 'brain')
    return accepted
  }
  const client = {
    async search(query = {}) {
      const body = await transport.request('brain.projection.search', { path: '/v2/projections/search', body: query })
      const projections = boundedList(responseBody(body, 'projections'), 'projections')
      return Object.freeze(projections.map((projection) => validateBrainProjection(projection)))
    },
    async read(projectionRef) {
      const body = await transport.request('brain.projection.read', {
        path: pathRef('/v2/projections/', projectionRef),
      })
      const accepted = validateBrainProjection(responseBody(body, 'projection'))
      if (accepted.projectionRef !== projectionRef) tampered('Brain returned a different projection', 'brain')
      return accepted
    },
    async createHandoff(input) {
      return handoff('brain.handoff.create', { path: '/v2/handoffs', body: input })
    },
    async readHandoff(handoffRef) {
      return handoff('brain.handoff.read', { path: pathRef('/v2/handoffs/', handoffRef), handoffRef })
    },
    async acceptHandoff(handoffRef) {
      return handoff('brain.handoff.accept', { path: pathRef('/v2/handoffs/', handoffRef) + '/accept', handoffRef })
    },
    async handoffStatus(handoffRef) {
      return handoff('brain.handoff.status', { path: pathRef('/v2/handoffs/', handoffRef) + '/status', handoffRef })
    },
    async closeHandoff(handoffRef) {
      return handoff('brain.handoff.close', { path: pathRef('/v2/handoffs/', handoffRef) + '/close', handoffRef })
    },
  }
  client.searchProjections = client.search
  client.readProjection = client.read
  return Object.freeze(client)
}

function skillsClient(transport) {
  const client = {
    async search(query = {}) {
      const body = await transport.request('skills.release.search', { path: '/v2/releases/search', body: query })
      const releases = boundedList(responseBody(body, 'releases'), 'releases')
      return Object.freeze(releases.map((release) => validateSkillsRelease(release)))
    },
    async read(release) {
      const body = await transport.request('skills.release.read', {
        path: `/v2/releases/${encodeURIComponent(release.skillId)}/${encodeURIComponent(release.version)}`,
      })
      const accepted = validateSkillsRelease(responseBody(body, 'release'))
      if (accepted.skillId !== release.skillId || accepted.version !== release.version || accepted.releaseHash !== release.releaseHash) {
        tampered('Skills returned a different release', 'skills')
      }
      return accepted
    },
    async readFragment(release, fragmentLevel) {
      const body = await transport.request('skills.release.fragment.read', {
        path: `/v2/releases/${encodeURIComponent(release.skillId)}/${encodeURIComponent(release.version)}/fragments/${fragmentLevel}`,
      })
      const accepted = validateSkillsRelease(responseBody(body, 'release'))
      if (accepted.skillId !== release.skillId || accepted.version !== release.version || accepted.releaseHash !== release.releaseHash) {
        tampered('Skills returned a different fragment release', 'skills')
      }
      return accepted
    },
    async submitTelemetry(report) {
      const body = await transport.request('skills.telemetry.submit', { path: '/v2/telemetry', body: report })
      return validateSkillsTelemetry(responseBody(body, 'report'))
    },
  }
  client.discover = client.search
  return Object.freeze(client)
}

function librariesClient(transport) {
  const client = {
    async search(query = {}) {
      const body = await transport.request('libraries.catalogue.search', { path: '/v2/catalogue/search', body: query })
      const entries = boundedList(responseBody(body, 'entries'), 'entries')
      return Object.freeze(entries.map((entry) => validateLibraryReference(entry)))
    },
    async read(reference) {
      const requested = validateLibraryReference(reference)
      const body = await transport.request('libraries.entry.read', {
        path: `/v2/entries/${encodeURIComponent(requested.entryId)}/${encodeURIComponent(requested.version)}`,
      })
      const accepted = validateLibraryReference(responseBody(body, 'entry'))
      if (accepted.entryId !== requested.entryId || accepted.version !== requested.version) {
        tampered('LiNKlibraries returned a different entry', 'libraries')
      }
      return accepted
    },
  }
  client.discover = client.search
  return Object.freeze(client)
}

function autoworkClient(transport, now) {
  const client = {
    async submit(request, options = {}) {
      const accepted = validateAutoworkRequest(request, { ...options, now: options.now ?? now ?? Date.now() })
      const body = await transport.request('autowork.request.submit', { path: '/v1/requests', body: request })
      if (!body?.request) return accepted
      const returned = validateAutoworkRequest(body.request, { ...options, now: options.now ?? now ?? Date.now() })
      if (returned.requestId !== accepted.requestId || returned.fingerprint !== accepted.fingerprint) {
        tampered('Autowork returned a different request', 'autowork')
      }
      return returned
    },
    async readStatus({ requestId, previousStatus } = {}) {
      try {
        const body = await transport.request('autowork.status.read', {
          path: pathRef('/v1/requests/', requestId) + '/status',
        })
        const accepted = validateAutoworkStatus(responseBody(body, 'status'), { previousStatus })
        if (accepted.requestId !== requestId) tampered('Autowork returned a different status request', 'autowork')
        return accepted
      } catch (error) {
        return holdAutowork(error)
      }
    },
    async readHandoff(requestId) {
      try {
        const body = await transport.request('autowork.handoff.read', {
          path: pathRef('/v1/requests/', requestId) + '/handoff',
        })
        const accepted = validateAutoworkHandoff(responseBody(body, 'handoff'))
        return accepted
      } catch (error) {
        return holdAutowork(error)
      }
    },
    async readReceipt({ requestId, request, fingerprint } = {}) {
      try {
        const body = await transport.request('autowork.receipt.read', {
          path: pathRef('/v1/requests/', requestId) + '/receipt',
        })
        const accepted = validateAutoworkReceipt(responseBody(body, 'receipt'), {
          request,
          fingerprint,
          now: now ?? Date.now(),
        })
        if (accepted.requestId !== requestId) tampered('Autowork returned a different receipt request', 'autowork')
        return accepted
      } catch (error) {
        return holdAutowork(error)
      }
    },
  }
  client.submitRequest = client.submit
  return Object.freeze(client)
}

export const createPlatformClient = platformClient
export const createBrainClient = brainClient
export const createSkillsClient = skillsClient
export const createLibrariesClient = librariesClient
export const createAutoworkClient = autoworkClient

/**
 * Create the five bounded provider clients.
 *
 * Pass prebuilt transports in focused tests, or pass validated runtime config
 * and a credential resolver for authenticated operation.
 */
export function createProviderClients(options = {}) {
  let transports = options.transports
  if (!transports) {
    const config = validateProviderRuntimeConfig(options.config)
    transports = createTransports(config, options)
  }
  return Object.freeze({
    platform: platformClient(transportFor(transports, 'platform'), options.now),
    brain: brainClient(transportFor(transports, 'brain')),
    skills: skillsClient(transportFor(transports, 'skills')),
    libraries: librariesClient(transportFor(transports, 'libraries')),
    autowork: autoworkClient(transportFor(transports, 'autowork'), options.now),
  })
}
