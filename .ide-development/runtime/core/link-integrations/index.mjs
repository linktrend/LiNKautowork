/**
 * Public barrel for the IDE Development five-provider consumer boundary.
 *
 * Re-exports S0–S6 modules after platform, libraries, brain, skills, and
 * autowork validators exist. This barrel has no transport, credentials, Git
 * write, Ledger, Gate mutation, or self-install helpers.
 */

export { ConsumerContractError, fail } from './errors.mjs'
export {
  FROZEN_PROVIDER_KEYS,
  FROZEN_PROVIDERS,
  PIN_AUTHORITY,
} from './pins.mjs'
export {
  PLATFORM_AUTH_CLAIMS_CONTRACT_VERSION,
  PLATFORM_PIN,
  validatePlatformIdentity,
} from './platform.mjs'
export { validateLibraryReference } from './libraries.mjs'
export {
  BRAIN_CONTRACT_VERSION,
  BRAIN_PIN,
  validateBrainHandoff,
  validateBrainProjection,
} from './brain.mjs'
export {
  SKILLS_CONTRACT_VERSION,
  SKILLS_PIN,
  validateSkillsRelease,
  validateSkillsTelemetry,
} from './skills.mjs'
export {
  ACTIVE_COPY_COUNT,
  SKILLS_LOCK_CONTRACT_VERSION,
  SKILLS_LOCK_PACKET,
  V24_ROLLBACK_COMMIT,
  V24_ROLLBACK_TREE,
  loadSkillsLock,
  planPhysicalSkillRemoval,
  recordSkillsTelemetry,
  retrieveSkillFragment,
} from './skills-loader.mjs'
export {
  AUTOWORK_AUDIENCE,
  AUTOWORK_CONTRACT_VERSION,
  AUTOWORK_EXECUTION_AUTHORITY,
  AUTOWORK_PIN,
  autoworkRequestFingerprint,
  validateAutoworkCallback,
  validateAutoworkHandoff,
  validateAutoworkReceipt,
  validateAutoworkRequest,
  validateAutoworkStatus,
} from './autowork.mjs'
export {
  MCP_PROTOCOL_VERSION,
  OKF_FORMAT,
  OKF_VERSION,
  negotiateMcp,
  validateOkfMapping,
} from './mcp.mjs'
export {
  PROVIDER_RUNTIME_CONFIG_VERSION,
  validateProviderRuntimeConfig,
  validateRuntimeConfig,
} from './config.mjs'
export {
  PROVIDER_REGISTRY,
  PROVIDER_REGISTRY_VERSION,
  getProviderDefinition,
  getProviderTool,
  validateProviderRegistry,
} from './registry.mjs'
export { REDACTION_LIMITS, redact, redactError } from './redaction.mjs'
export {
  ProviderTransportError,
  createAuthenticatedTransport,
  createProviderTransport,
  createTransports,
} from './transport.mjs'
export {
  createAutoworkClient,
  createBrainClient,
  createLibrariesClient,
  createPlatformClient,
  createProviderClients,
  createSkillsClient,
} from './clients.mjs'
