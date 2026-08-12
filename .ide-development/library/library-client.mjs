#!/usr/bin/env node
/**
 * Portable LiNKlibraries consumer client.
 *
 * The Library is a Git-backed registry, not a runtime dependency.  Every
 * successful read is bound to one immutable catalog commit and an entry at
 * that same commit.  Cache bytes are disposable; verification metadata is
 * authoritative only after it has been revalidated.
 */
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { validSpdxExpression } from './vendor/spdx-expression-validate.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const DEFAULT_REPO = process.env.LINKTREND_SHARED_LIBRARY_REPO_URL ?? 'https://github.com/linktrend/LiNKlibraries.git'
const DEFAULT_BRANCH = process.env.LINKTREND_SHARED_LIBRARY_BASE_BRANCH ?? 'development'
const DEFAULT_CACHE = process.env.LINKTREND_SHARED_LIBRARY_CHECKOUT ?? join(HERE, '.cache', 'linklibraries')
const SCHEMA_DIR = join(HERE, 'schemas')
const SHA_RE = /^[a-f0-9]{40}$/
const HASH_RE = /^[a-f0-9]{64}$/
const ENTRY_ID_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
const MAX_FILES = 256
const MAX_FILE_BYTES = 5 * 1024 * 1024
const MAX_TOTAL_BYTES = 25 * 1024 * 1024
const ENTRY_STATES = new Set(['usable', 'metadata_only', 'deprecated', 'quarantined', 'superseded'])
const ENTRY_KINDS = new Set(['custom_component', 'code_pattern', 'template', 'starter_kit', 'vetted_oss'])
const CONTENT_MODES = new Set(['executable', 'documentation'])
const RUNNERS = new Set(['node:test', 'tsx', 'vitest', 'jest', 'pytest'])
const PACKAGE_ECOSYSTEMS = new Set(['npm', 'pypi', 'cargo', 'go', 'maven', 'nuget', 'other'])

export class LibraryClientError extends Error {
  constructor(code, message, details = {}) {
    super(message)
    this.name = 'LibraryClientError'
    this.code = code
    this.details = details
  }
}

function fail(code, message, details = {}) {
  throw new LibraryClientError(code, message, details)
}

function run(cmd, args, cwd) {
  try {
    return execFileSync(cmd, args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  } catch (error) {
    const stderr = String(error?.stderr ?? '').trim().replace(/\s+/g, ' ').slice(0, 500)
    fail('git_operation_failed', `${cmd} ${args.join(' ')} failed${stderr ? `: ${stderr}` : ''}`)
  }
}

function ensureDir(path) {
  mkdirSync(path, { recursive: true })
}

function writeJsonAtomic(path, value) {
  ensureDir(dirname(path))
  const temp = `${path}.tmp-${process.pid}`
  writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
  renameSync(temp, path)
}

function readJson(path, label) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    fail('invalid_json', `${label} is not valid JSON`, { path, detail: String(error.message ?? error) })
  }
}

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex')
}

function sha256File(path) {
  return sha256Bytes(readFileSync(path))
}

function hashField(value, label) {
  if (typeof value !== 'string' || !HASH_RE.test(value)) fail('schema_validation_failed', `${label} must be a lowercase SHA-256 hex string`)
  return value
}

function stringField(value, label) {
  if (typeof value !== 'string' || value.length === 0) fail('schema_validation_failed', `${label} must be a non-empty string`)
  return value
}

function arrayField(value, label, { min = 0 } = {}) {
  if (!Array.isArray(value) || value.length < min || value.some((item) => typeof item !== 'string' || item.length === 0)) {
    fail('schema_validation_failed', `${label} must be an array of non-empty strings`)
  }
  return value
}

function objectField(value, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail('schema_validation_failed', `${label} must be an object`)
  return value
}

function assertKeys(value, allowed, label) {
  for (const key of Object.keys(value)) if (!allowed.has(key)) fail('schema_validation_failed', `${label} contains unsupported field: ${key}`)
}

const schemaCache = new Map()

function loadSchema(name) {
  if (!schemaCache.has(name)) schemaCache.set(name, readJson(join(SCHEMA_DIR, name), `packaged schema ${name}`))
  return schemaCache.get(name)
}

function schemaTypeMatches(value, type) {
  if (type === 'object') return value !== null && typeof value === 'object' && !Array.isArray(value)
  if (type === 'array') return Array.isArray(value)
  if (type === 'integer') return typeof value === 'number' && Number.isInteger(value)
  if (type === 'number') return typeof value === 'number' && Number.isFinite(value)
  if (type === 'string') return typeof value === 'string'
  if (type === 'boolean') return typeof value === 'boolean'
  if (type === 'null') return value === null
  return false
}

function equalJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right)
}

function validDateTime(value) {
  const match = typeof value === 'string' && value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/)
  if (!match) return false
  const [, year, month, day, hour, minute, second, offset] = match
  const monthNumber = Number(month)
  const dayNumber = Number(day)
  const hourNumber = Number(hour)
  const minuteNumber = Number(minute)
  const secondNumber = Number(second)
  const offsetMatch = offset === 'Z' ? null : offset.match(/^[+-](\d{2}):(\d{2})$/)
  return monthNumber >= 1 && monthNumber <= 12
    && dayNumber >= 1 && dayNumber <= new Date(Date.UTC(Number(year), monthNumber, 0)).getUTCDate()
    && hourNumber <= 23 && minuteNumber <= 59 && secondNumber <= 59
    && (!offsetMatch || (Number(offsetMatch[1]) <= 23 && Number(offsetMatch[2]) <= 59))
}

function validFormat(value, format) {
  if (format === 'date-time') return validDateTime(value)
  if (format === 'uri') {
    try {
      return typeof value === 'string' && Boolean(new URL(value).protocol)
    } catch {
      return false
    }
  }
  if (format === 'spdx-expression') return validSpdxExpression(value)
  return false
}

function resolveSchemaRef(root, ref) {
  if (!ref.startsWith('#/')) return null
  return ref.slice(2).split('/').reduce((value, part) => value?.[part.replace(/~1/g, '/').replace(/~0/g, '~')], root)
}

function schemaErrors(value, schema, root, path = '$', errors = []) {
  if (schema === true) return errors
  if (schema === false) {
    errors.push({ path, keyword: 'falseSchema' })
    return errors
  }
  if (schema.$ref) {
    const target = resolveSchemaRef(root, schema.$ref)
    if (!target) errors.push({ path, keyword: '$ref', detail: schema.$ref })
    else schemaErrors(value, target, root, path, errors)
    return errors
  }
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type]
    if (!types.some((type) => schemaTypeMatches(value, type))) {
      errors.push({ path, keyword: 'type', expected: types })
      return errors
    }
  }
  if (schema.const !== undefined && !equalJson(value, schema.const)) errors.push({ path, keyword: 'const', expected: schema.const })
  if (schema.enum !== undefined && !schema.enum.some((item) => equalJson(value, item))) errors.push({ path, keyword: 'enum' })
  if (typeof value === 'string') {
    if (schema.minLength !== undefined && Array.from(value).length < schema.minLength) errors.push({ path, keyword: 'minLength' })
    if (schema.maxLength !== undefined && Array.from(value).length > schema.maxLength) errors.push({ path, keyword: 'maxLength' })
    if (schema.pattern !== undefined) {
      try {
        if (!new RegExp(schema.pattern).test(value)) errors.push({ path, keyword: 'pattern' })
      } catch {
        errors.push({ path, keyword: 'invalidPattern' })
      }
    }
    if (schema.format !== undefined && !validFormat(value, schema.format)) errors.push({ path, keyword: 'format', format: schema.format })
  }
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push({ path, keyword: 'minimum' })
    if (schema.maximum !== undefined && value > schema.maximum) errors.push({ path, keyword: 'maximum' })
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push({ path, keyword: 'minItems' })
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push({ path, keyword: 'maxItems' })
    if (schema.items !== undefined) value.forEach((item, index) => schemaErrors(item, schema.items, root, `${path}[${index}]`, errors))
  }
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const properties = schema.properties ?? {}
    for (const required of schema.required ?? []) if (!Object.prototype.hasOwnProperty.call(value, required)) errors.push({ path, keyword: 'required', property: required })
    for (const [key, propertySchema] of Object.entries(properties)) if (Object.prototype.hasOwnProperty.call(value, key)) schemaErrors(value[key], propertySchema, root, `${path}.${key}`, errors)
    if (schema.additionalProperties !== undefined) {
      for (const [key, propertyValue] of Object.entries(value)) {
        if (Object.prototype.hasOwnProperty.call(properties, key)) continue
        if (schema.additionalProperties === false) errors.push({ path: `${path}.${key}`, keyword: 'additionalProperties' })
        else schemaErrors(propertyValue, schema.additionalProperties, root, `${path}.${key}`, errors)
      }
    }
  }
  for (const subschema of schema.allOf ?? []) schemaErrors(value, subschema, root, path, errors)
  if (schema.anyOf) {
    const valid = schema.anyOf.some((subschema) => schemaErrors(value, subschema, root, path, []).length === 0)
    if (!valid) errors.push({ path, keyword: 'anyOf' })
  }
  if (schema.oneOf) {
    const matches = schema.oneOf.filter((subschema) => schemaErrors(value, subschema, root, path, []).length === 0).length
    if (matches !== 1) errors.push({ path, keyword: 'oneOf' })
  }
  if (schema.if !== undefined) {
    const conditionMatches = schemaErrors(value, schema.if, root, path, []).length === 0
    if (conditionMatches && schema.then !== undefined) schemaErrors(value, schema.then, root, path, errors)
    if (!conditionMatches && schema.else !== undefined) schemaErrors(value, schema.else, root, path, errors)
  }
  if (schema.not !== undefined && schemaErrors(value, schema.not, root, path, []).length === 0) errors.push({ path, keyword: 'not' })
  return errors
}

function validatePackagedSchema(value, schemaName, label) {
  const schema = loadSchema(schemaName)
  const errors = schemaErrors(value, schema, schema)
  if (errors.length > 0) fail('schema_validation_failed', `${label} does not satisfy packaged ${schemaName}`, { schema: schemaName, errors: errors.slice(0, 20) })
}

function safeRelativePath(value) {
  if (typeof value !== 'string' || value.length === 0 || value.includes('\0') || value.startsWith('/') || value.startsWith('\\') || /^[A-Za-z]:/.test(value) || value.includes('\\')) return false
  return value.split('/').every((part) => part.length > 0 && part !== '.' && part !== '..')
}

function pathInside(root, path) {
  const rootAbs = resolve(root)
  const pathAbs = resolve(path)
  const rel = relative(rootAbs, pathAbs)
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !rel.startsWith(sep))
}

function parseVersion(value, { partial = false } = {}) {
  const match = String(value ?? '').trim().match(new RegExp(`^v?(\\d+)(?:\\.(\\d+))?(?:\\.(\\d+))?$`))
  if (!match || (!partial && (match[2] === undefined || match[3] === undefined))) return null
  return { value: [Number(match[1]), Number(match[2] ?? 0), Number(match[3] ?? 0)], parts: match[3] === undefined ? (match[2] === undefined ? 1 : 2) : 3 }
}

function compareVersions(left, right) {
  for (let index = 0; index < 3; index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index]
  }
  return 0
}

function rangeFailure(kind, detail) {
  return { ok: false, kind, detail }
}

function bound(version, inclusive) {
  return { version, inclusive }
}

function intersectBounds(current, next, lower) {
  if (!current) return next
  const comparison = compareVersions(current.version, next.version)
  if ((lower && comparison < 0) || (!lower && comparison > 0)) return next
  if (comparison !== 0) return current
  return bound(current.version, current.inclusive && next.inclusive)
}

function parseVersionRange(range) {
  if (typeof range !== 'string' || range.trim() === '') return rangeFailure('malformed', 'range must be a non-empty string')
  const text = range.trim()
  if (/\*|\bx\b|\bX\b|\blatest\b|\bworkspace:|\bfile:|\bgithub:/i.test(text)) return rangeFailure('unsupported', 'wildcard, workspace, file, github, and tag ranges are unsupported')
  const alternatives = text.split('||')
  if (alternatives.some((alternative) => alternative.trim() === '')) return rangeFailure('malformed', 'range contains an empty alternative')
  const parsed = []
  for (const alternative of alternatives) {
    const tokens = alternative.trim().split(/\s+/)
    let lower = null
    let upper = null
    for (const token of tokens) {
      const match = token.match(/^(>=|<=|>|<|=|\^|~)?(v?\d+(?:\.\d+){0,2})$/)
      if (!match) {
        if (/^[~^]/.test(token) || /[-*+]/.test(token)) return rangeFailure('unsupported', `unsupported range token: ${token}`)
        return rangeFailure('malformed', `malformed range token: ${token}`)
      }
      const operator = match[1] ?? '='
      const parsedVersion = parseVersion(match[2], { partial: true })
      if (!parsedVersion) return rangeFailure('malformed', `malformed version token: ${token}`)
      const version = parsedVersion.value
      if ((operator === '^' || operator === '~') && parsedVersion.parts !== 3) return rangeFailure('unsupported', `${operator} requires a complete major.minor.patch version`)
      if (operator === '^') {
        let next
        if (version[0] > 0) next = [version[0] + 1, 0, 0]
        else if (version[1] > 0) next = [0, version[1] + 1, 0]
        else next = [0, 0, version[2] + 1]
        lower = intersectBounds(lower, bound(version, true), true)
        upper = intersectBounds(upper, bound(next, false), false)
      } else if (operator === '~') {
        lower = intersectBounds(lower, bound(version, true), true)
        upper = intersectBounds(upper, bound([version[0], version[1] + 1, 0], false), false)
      } else if (operator === '>=') lower = intersectBounds(lower, bound(version, true), true)
      else if (operator === '>') lower = intersectBounds(lower, bound(version, false), true)
      else if (operator === '<=') upper = intersectBounds(upper, bound(version, true), false)
      else if (operator === '<') upper = intersectBounds(upper, bound(version, false), false)
      else {
        if (parsedVersion.parts !== 3) return rangeFailure('unsupported', 'exact ranges require a complete major.minor.patch version')
        lower = intersectBounds(lower, bound(version, true), true)
        upper = intersectBounds(upper, bound(version, true), false)
      }
    }
    parsed.push({ lower, upper })
  }
  return { ok: true, alternatives: parsed }
}

function intervalHasVersion(interval, version) {
  if (interval.lower) {
    const comparison = compareVersions(version, interval.lower.version)
    if (comparison < 0 || (comparison === 0 && !interval.lower.inclusive)) return false
  }
  if (interval.upper) {
    const comparison = compareVersions(version, interval.upper.version)
    if (comparison > 0 || (comparison === 0 && !interval.upper.inclusive)) return false
  }
  return true
}

function intervalsIntersect(left, right) {
  const lower = intersectBounds(left.lower, right.lower, true)
  const upper = intersectBounds(left.upper, right.upper, false)
  if (!lower || !upper) return true
  const comparison = compareVersions(lower.version, upper.version)
  return comparison < 0 || (comparison === 0 && lower.inclusive && upper.inclusive)
}

function satisfiesVersion(version, range) {
  const actual = parseVersion(version)
  const parsed = typeof range === 'object' && range?.ok !== undefined ? range : parseVersionRange(range)
  return Boolean(actual && parsed.ok && parsed.alternatives.some((alternative) => intervalHasVersion(alternative, actual.value)))
}

function rangeCompatibilityError(code, name, required, declared, detail) {
  return { code, name, required, ...(declared === undefined ? {} : { declared }), detail }
}

function validateCompatibility(value, label) {
  objectField(value, label)
  assertKeys(value, new Set(['node', 'runtimes', 'operatingSystems']), label)
  stringField(value.node, `${label}.node`)
  arrayField(value.runtimes, `${label}.runtimes`, { min: 1 })
  if (value.operatingSystems !== undefined) arrayField(value.operatingSystems, `${label}.operatingSystems`)
}

function validateDependencies(value, label) {
  objectField(value, label)
  assertKeys(value, new Set(['packages', 'services']), label)
  if (!Array.isArray(value.packages) || !Array.isArray(value.services)) fail('schema_validation_failed', `${label} requires packages and services arrays`)
  for (const dependency of value.packages) {
    objectField(dependency, `${label}.packages[]`)
    assertKeys(dependency, new Set(['name', 'version', 'ecosystem', 'optional']), `${label}.packages[]`)
    stringField(dependency.name, 'dependency.name')
    stringField(dependency.version, 'dependency.version')
    if (!PACKAGE_ECOSYSTEMS.has(dependency.ecosystem)) fail('schema_validation_failed', `unsupported dependency ecosystem: ${dependency.ecosystem}`)
    if (dependency.optional !== undefined && typeof dependency.optional !== 'boolean') fail('schema_validation_failed', 'dependency.optional must be boolean')
  }
  for (const dependency of value.services) {
    objectField(dependency, `${label}.services[]`)
    assertKeys(dependency, new Set(['name', 'purpose', 'required']), `${label}.services[]`)
    stringField(dependency.name, 'service.name')
    stringField(dependency.purpose, 'service.purpose')
    if (typeof dependency.required !== 'boolean') fail('schema_validation_failed', 'service.required must be boolean')
  }
}

function validateEntryDocument(entry, label = 'entry') {
  validatePackagedSchema(entry, 'library-entry.schema.json', label)
  objectField(entry, label)
  assertKeys(entry, new Set(['schemaVersion', 'entryId', 'kind', 'name', 'summary', 'problemDomains', 'tags', 'languages', 'frameworks', 'state', 'contentMode', 'selectable', 'compatibility', 'dependencies', 'testContract', 'license', 'securityReview', 'usage', 'integrationNotes', 'gotchas', 'provenance', 'files', 'supersededBy', 'quarantine', 'deprecation']), label)
  if (entry.schemaVersion !== 2) fail('schema_validation_failed', `${label}.schemaVersion must be 2`)
  if (typeof entry.entryId !== 'string' || !ENTRY_ID_RE.test(entry.entryId) || entry.entryId.length < 2 || entry.entryId.length > 128) fail('schema_validation_failed', `${label}.entryId is invalid`)
  if (!ENTRY_KINDS.has(entry.kind)) fail('schema_validation_failed', `${label}.kind is invalid`)
  for (const key of ['name', 'summary', 'integrationNotes']) stringField(entry[key], `${label}.${key}`)
  for (const key of ['problemDomains', 'tags', 'languages', 'frameworks']) arrayField(entry[key], `${label}.${key}`, { min: key === 'problemDomains' ? 1 : 0 })
  if (!ENTRY_STATES.has(entry.state)) fail('schema_validation_failed', `${label}.state is invalid`)
  if (!CONTENT_MODES.has(entry.contentMode) || typeof entry.selectable !== 'boolean') fail('schema_validation_failed', `${label}.contentMode/selectable is invalid`)
  validateCompatibility(entry.compatibility, `${label}.compatibility`)
  validateDependencies(entry.dependencies, `${label}.dependencies`)
  objectField(entry.license, `${label}.license`)
  assertKeys(entry.license, new Set(['spdx', 'redistributionAllowed', 'notes']), `${label}.license`)
  stringField(entry.license.spdx, `${label}.license.spdx`)
  if (typeof entry.license.redistributionAllowed !== 'boolean') fail('schema_validation_failed', `${label}.license.redistributionAllowed must be boolean`)
  objectField(entry.securityReview, `${label}.securityReview`)
  assertKeys(entry.securityReview, new Set(['reviewedAt', 'reviewedBy', 'notes']), `${label}.securityReview`)
  for (const key of ['reviewedAt', 'reviewedBy', 'notes']) stringField(entry.securityReview[key], `${label}.securityReview.${key}`)
  if (Number.isNaN(Date.parse(entry.securityReview.reviewedAt))) fail('schema_validation_failed', `${label}.securityReview.reviewedAt must be date-time`)
  objectField(entry.usage, `${label}.usage`)
  assertKeys(entry.usage, new Set(['howToUse', 'examples']), `${label}.usage`)
  stringField(entry.usage.howToUse, `${label}.usage.howToUse`)
  if (entry.usage.examples !== undefined) arrayField(entry.usage.examples, `${label}.usage.examples`)
  arrayField(entry.gotchas, `${label}.gotchas`)
  objectField(entry.provenance, `${label}.provenance`)
  assertKeys(entry.provenance, new Set(['sourceSystem', 'sourceRevisionSha', 'contributedAt', 'sourceUrl', 'versionOrRange', 'productRunId', 'pullRequestNumber', 'pullRequestUrl']), `${label}.provenance`)
  if (!new Set(['ide-development', 'linkdeveloper', 'manual', 'migration']).has(entry.provenance.sourceSystem)) fail('schema_validation_failed', `${label}.provenance.sourceSystem is invalid`)
  if (!/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(entry.provenance.sourceRevisionSha)) fail('schema_validation_failed', `${label}.provenance.sourceRevisionSha is invalid`)
  if (Number.isNaN(Date.parse(entry.provenance.contributedAt))) fail('schema_validation_failed', `${label}.provenance.contributedAt must be date-time`)
  for (const key of ['sourceUrl', 'pullRequestUrl']) {
    if (entry.provenance[key] !== undefined) {
      try { new URL(entry.provenance[key]) } catch { fail('schema_validation_failed', `${label}.provenance.${key} must be a URI`) }
    }
  }
  for (const key of ['versionOrRange', 'productRunId']) {
    if (entry.provenance[key] !== undefined) stringField(entry.provenance[key], `${label}.provenance.${key}`)
  }
  if (entry.provenance.pullRequestNumber !== undefined && (!Number.isInteger(entry.provenance.pullRequestNumber) || entry.provenance.pullRequestNumber < 1)) {
    fail('schema_validation_failed', `${label}.provenance.pullRequestNumber must be a positive integer`)
  }
  if (!Array.isArray(entry.files) || entry.files.length < 1) fail('schema_validation_failed', `${label}.files must be non-empty`)
  if (!entry.files.some((file) => file.path === 'README.md')) fail('schema_validation_failed', `${label}.files must include README.md`)
  const paths = new Set()
  for (const file of entry.files) {
    objectField(file, `${label}.files[]`)
    assertKeys(file, new Set(['path', 'sha256']), `${label}.files[]`)
    if (!safeRelativePath(file.path) || file.path === 'entry.json') fail('schema_validation_failed', `${label}.files contains unsafe path`)
    if (paths.has(file.path)) fail('schema_validation_failed', `${label}.files contains duplicate path: ${file.path}`)
    paths.add(file.path)
    hashField(file.sha256, `${label}.files[${file.path}].sha256`)
  }
  if (entry.testContract !== undefined) {
    objectField(entry.testContract, `${label}.testContract`)
    assertKeys(entry.testContract, new Set(['runner', 'files', 'timeoutMs']), `${label}.testContract`)
    if (!RUNNERS.has(entry.testContract.runner)) fail('schema_validation_failed', `${label}.testContract.runner is not allowlisted`)
    arrayField(entry.testContract.files, `${label}.testContract.files`, { min: 1 })
    if (!Number.isInteger(entry.testContract.timeoutMs) || entry.testContract.timeoutMs < 1 || entry.testContract.timeoutMs > 300000) fail('schema_validation_failed', `${label}.testContract.timeoutMs is invalid`)
    for (const file of entry.testContract.files) if (!paths.has(file)) fail('schema_validation_failed', `test contract file is not declared: ${file}`)
  }
  for (const file of entry.files) if (file.path === 'entry.json') fail('schema_validation_failed', 'entry.json cannot be a payload file')
  if (entry.state === 'rejected') fail('entry_not_admissible', 'rejected entries are not production entries')
  if (entry.state === 'metadata_only' && (entry.contentMode !== 'documentation' || entry.selectable || entry.testContract || entry.dependencies.packages.length || entry.dependencies.services.length)) fail('entry_state_invalid', 'metadata_only entries must be documentation-only, non-selectable, dependency-free, and untested')
  if (entry.state === 'usable' && entry.contentMode === 'executable' && (!entry.files.some((file) => file.path.startsWith('assets/')) || !entry.testContract)) fail('entry_state_invalid', 'usable executable entries require assets and a test contract')
  if (entry.state === 'usable' && entry.contentMode === 'documentation' && !new Set(['template', 'code_pattern', 'vetted_oss']).has(entry.kind)) fail('entry_state_invalid', 'usable documentation entry kind is not reusable')
  if (entry.state === 'superseded' && entry.supersededBy === entry.entryId) fail('entry_state_invalid', 'supersededBy cannot reference the same entry')
  return entry
}

function projectCatalogEntry(entry) {
  const result = {}
  for (const key of ['entryId', 'kind', 'name', 'summary', 'problemDomains', 'tags', 'languages', 'frameworks', 'state', 'contentMode', 'selectable', 'compatibility', 'dependencies']) result[key] = entry[key]
  if (entry.supersededBy !== undefined) result.supersededBy = entry.supersededBy
  result.path = `entries/${entry.entryId}`
  return result
}

function validateCatalogDocument(catalog) {
  validatePackagedSchema(catalog, 'catalog.schema.json', 'catalog')
  objectField(catalog, 'catalog')
  assertKeys(catalog, new Set(['schemaVersion', 'entriesSha256', 'entries']), 'catalog')
  if (catalog.schemaVersion !== 2 || !HASH_RE.test(catalog.entriesSha256) || !Array.isArray(catalog.entries)) fail('catalog_schema_invalid', 'catalog must satisfy schema v2')
  const ids = new Set()
  for (let index = 0; index < catalog.entries.length; index += 1) {
    const row = catalog.entries[index]
    objectField(row, `catalog.entries[${index}]`)
    assertKeys(row, new Set(['entryId', 'kind', 'name', 'summary', 'problemDomains', 'tags', 'languages', 'frameworks', 'state', 'contentMode', 'selectable', 'compatibility', 'dependencies', 'supersededBy', 'path']), `catalog.entries[${index}]`)
    for (const key of ['entryId', 'kind', 'name', 'summary', 'state', 'contentMode', 'path']) stringField(row[key], `catalog.entries[${index}].${key}`)
    if (!ENTRY_ID_RE.test(row.entryId) || ids.has(row.entryId)) fail('catalog_semantic_invalid', `catalog entryId is duplicate or invalid: ${row.entryId}`)
    ids.add(row.entryId)
    if (!ENTRY_KINDS.has(row.kind) || !ENTRY_STATES.has(row.state) || !CONTENT_MODES.has(row.contentMode) || typeof row.selectable !== 'boolean') fail('catalog_schema_invalid', `catalog row is invalid: ${row.entryId}`)
    if (row.path !== `entries/${row.entryId}`) fail('catalog_entry_path_mismatch', `catalog path does not match entryId: ${row.entryId}`)
    validateCompatibility(row.compatibility, `catalog.entries[${index}].compatibility`)
    validateDependencies(row.dependencies, `catalog.entries[${index}].dependencies`)
    if (row.state === 'metadata_only' && row.selectable) fail('metadata_only_selection_forbidden', `metadata-only entry is selectable: ${row.entryId}`)
    if (index > 0 && catalog.entries[index - 1].entryId.localeCompare(row.entryId) > 0) fail('catalog_not_sorted', 'catalog entries must be sorted by entryId')
  }
  const digest = sha256Bytes(Buffer.from(JSON.stringify(catalog.entries), 'utf8'))
  if (digest !== catalog.entriesSha256) fail('catalog_digest_mismatch', 'catalog entriesSha256 does not match entries', { expected: digest, actual: catalog.entriesSha256 })
  return catalog
}

function listPayloadFiles(root) {
  const files = []
  const walk = (directory, prefix = '') => {
    for (const item of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const path = join(directory, item.name)
      const rel = prefix ? `${prefix}/${item.name}` : item.name
      const info = lstatSync(path)
      if ((item.name === 'entry.json' && prefix === '') || (item.name === 'verification.json' && prefix === '')) continue
      if (info.isSymbolicLink()) fail('symlink_payload', `payload symlink is not allowed: ${rel}`)
      if (info.isDirectory()) walk(path, rel)
      else if (info.isFile()) {
        if (files.length >= MAX_FILES) fail('payload_file_count_exceeded', `payload exceeds ${MAX_FILES} files`)
        if (info.size > MAX_FILE_BYTES) fail('payload_file_too_large', `payload file exceeds ${MAX_FILE_BYTES} bytes: ${rel}`)
        files.push({ path: rel, absolute: path, size: info.size })
      } else fail('non_regular_payload', `payload is not a regular file: ${rel}`)
    }
  }
  walk(root)
  const total = files.reduce((sum, file) => sum + file.size, 0)
  if (total > MAX_TOTAL_BYTES) fail('payload_aggregate_size_exceeded', `payload exceeds ${MAX_TOTAL_BYTES} bytes`)
  return files
}

function verifyEntryPayload(entry, entryRoot) {
  if (!pathInside(entryRoot, entryRoot)) fail('path_escape', 'entry root is unsafe')
  const actual = listPayloadFiles(entryRoot)
  const declared = new Map(entry.files.map((file) => [file.path, file.sha256]))
  for (const file of actual) {
    if (!declared.has(file.path)) fail('undeclared_payload', `payload file is not declared: ${file.path}`)
    const digest = sha256File(file.absolute)
    if (digest !== declared.get(file.path)) fail('payload_sha256_mismatch', `payload hash mismatch: ${file.path}`, { expected: declared.get(file.path), actual: digest })
  }
  for (const path of declared.keys()) if (!actual.some((file) => file.path === path)) fail('missing_declared_payload', `declared payload file is missing: ${path}`)
  return Object.fromEntries(actual.sort((a, b) => a.path.localeCompare(b.path)).map((file) => [file.path, sha256File(file.absolute)]))
}

function readConsumerPackage(root) {
  const path = join(resolve(root), 'package.json')
  if (!existsSync(path)) return null
  return readJson(path, 'consumer package.json')
}

function packageMap(packageJson) {
  return Object.assign({}, packageJson?.dependencies ?? {}, packageJson?.devDependencies ?? {}, packageJson?.peerDependencies ?? {})
}

function compatibilityReport(entry, { consumerRoot, runtime = 'node', nodeVersion = process.versions.node, frameworks, dependencies, services } = {}) {
  const errors = []
  if (!entry.compatibility.runtimes.includes(runtime)) errors.push({ code: 'runtime_incompatible', runtime, supported: entry.compatibility.runtimes })
  const nodeRange = parseVersionRange(entry.compatibility.node)
  if (!nodeRange.ok) errors.push(rangeCompatibilityError(`node_range_${nodeRange.kind}`, 'node', entry.compatibility.node, undefined, nodeRange.detail))
  else if (!parseVersion(nodeVersion)) errors.push({ code: 'node_version_malformed', nodeVersion })
  else if (!satisfiesVersion(nodeVersion, nodeRange)) errors.push({ code: 'node_incompatible', nodeVersion, required: entry.compatibility.node })
  const packageJson = consumerRoot ? readConsumerPackage(consumerRoot) : null
  const packages = dependencies ?? packageMap(packageJson)
  const availableFrameworks = new Set((frameworks ?? Object.keys(packages)).map((item) => String(item).toLowerCase()))
  const frameworkAliases = { react: ['react'], vue: ['vue'], angular: ['@angular/core'], next: ['next'], svelte: ['svelte'] }
  for (const framework of entry.frameworks) {
    const aliases = frameworkAliases[framework.toLowerCase()] ?? [framework]
    if (!aliases.some((alias) => availableFrameworks.has(alias.toLowerCase()))) errors.push({ code: 'framework_incompatible', framework })
  }
  for (const dependency of entry.dependencies.packages) {
    const declared = packages[dependency.name]
    if (dependency.ecosystem !== 'npm') {
      if (declared === undefined && !dependency.optional) errors.push({ code: 'dependency_missing', name: dependency.name, required: dependency.version })
      continue
    }
    const requiredRange = parseVersionRange(dependency.version)
    if (!requiredRange.ok) {
      errors.push(rangeCompatibilityError(`dependency_range_${requiredRange.kind}`, dependency.name, dependency.version, declared, requiredRange.detail))
      continue
    }
    if (declared === undefined) {
      if (!dependency.optional) errors.push({ code: 'dependency_missing', name: dependency.name, required: dependency.version })
      continue
    }
    const declaredRange = parseVersionRange(declared)
    if (!declaredRange.ok) {
      errors.push(rangeCompatibilityError(`dependency_declared_range_${declaredRange.kind}`, dependency.name, dependency.version, declared, declaredRange.detail))
      continue
    }
    if (!requiredRange.alternatives.some((required) => declaredRange.alternatives.some((available) => intervalsIntersect(required, available)))) {
      errors.push({ code: 'dependency_incompatible', name: dependency.name, required: dependency.version, declared })
    }
  }
  const availableServices = new Set((services ?? []).map((item) => String(item)))
  for (const dependency of entry.dependencies.services) if (dependency.required && !availableServices.has(dependency.name)) errors.push({ code: 'service_missing', name: dependency.name })
  return { ok: errors.length === 0, errors, nodeVersion, runtime, frameworkCount: entry.frameworks.length, dependencyCount: entry.dependencies.packages.length }
}

export class LibraryClient {
  constructor({
    repoUrl = DEFAULT_REPO,
    baseBranch = DEFAULT_BRANCH,
    cacheRoot = DEFAULT_CACHE,
    offline = process.env.LINKTREND_SHARED_LIBRARY_OFFLINE === '1',
    consumerRoot = process.env.LINKTREND_SHARED_LIBRARY_CONSUMER_ROOT,
    consumerId = process.env.LINKTREND_SHARED_LIBRARY_CONSUMER_ID ?? 'consumer',
    runId = process.env.LINKTREND_SHARED_LIBRARY_RUN_ID ?? 'local-run',
  } = {}) {
    this.repoUrl = repoUrl
    this.baseBranch = baseBranch
    this.cacheRoot = resolve(cacheRoot)
    this.offline = offline
    this.consumerRoot = consumerRoot ? resolve(consumerRoot) : undefined
    this.consumerId = consumerId
    this.runId = runId
    this.mirrorDir = join(this.cacheRoot, 'mirror')
    this.catalogCacheDir = join(this.cacheRoot, 'catalog')
    this.entryCacheDir = join(this.cacheRoot, 'entries')
    this.provenanceDir = join(this.cacheRoot, 'provenance')
    this.lastCatalog = null
    ensureDir(this.cacheRoot)
    ensureDir(this.catalogCacheDir)
    ensureDir(this.entryCacheDir)
    ensureDir(this.provenanceDir)
  }

  ensureMirror() {
    if (this.offline) {
      if (!existsSync(join(this.mirrorDir, '.git'))) fail('offline_mirror_missing', `Offline mirror is missing: ${this.mirrorDir}`)
      return
    }
    if (!existsSync(join(this.mirrorDir, '.git'))) {
      ensureDir(this.mirrorDir)
      run('git', ['clone', '--filter=blob:none', '--sparse', '--branch', this.baseBranch, '--single-branch', this.repoUrl, this.mirrorDir])
    } else run('git', ['-C', this.mirrorDir, 'fetch', 'origin', this.baseBranch])
  }

  checkoutCatalog() {
    this.ensureMirror()
    if (!this.offline) run('git', ['-C', this.mirrorDir, 'checkout', '-f', `origin/${this.baseBranch}`])
    if (!this.offline) run('git', ['-C', this.mirrorDir, 'sparse-checkout', 'set', 'indexes'])
  }

  tipSha() {
    const sha = run('git', ['-C', this.mirrorDir, 'rev-parse', 'HEAD'])
    if (!SHA_RE.test(sha)) fail('invalid_commit_sha', `Library tip is not an immutable commit SHA: ${sha}`)
    return sha
  }

  fetchCatalog() {
    if (this.offline) {
      const path = join(this.catalogCacheDir, 'latest.json')
      if (!existsSync(path)) fail('offline_catalog_missing', 'Offline catalog verification record is missing')
      const snapshot = readJson(path, 'cached catalog')
      if (!SHA_RE.test(snapshot.fetchCommitSha) || snapshot.catalogCommitSha !== snapshot.fetchCommitSha) fail('catalog_provenance_invalid', 'Cached catalog lacks one immutable commit binding')
      validateCatalogDocument(snapshot.catalog)
      const cachePath = join(this.catalogCacheDir, `${snapshot.fetchCommitSha}.json`)
      if (!existsSync(cachePath) || readFileSync(cachePath, 'utf8') !== readFileSync(path, 'utf8')) fail('catalog_cache_tampered', 'Cached latest catalog does not match its immutable snapshot')
      snapshot.stale = true
      this.lastCatalog = snapshot
      return snapshot
    }
    this.checkoutCatalog()
    const fetchCommitSha = this.tipSha()
    const catalogPath = join(this.mirrorDir, 'indexes', 'catalog.json')
    if (!existsSync(catalogPath)) fail('catalog_missing', 'Library authority does not contain indexes/catalog.json')
    const catalog = readJson(catalogPath, 'authority catalog')
    validateCatalogDocument(catalog)
    const snapshot = { schemaVersion: 1, fetchCommitSha, catalogCommitSha: fetchCommitSha, catalog, stale: false }
    writeJsonAtomic(join(this.catalogCacheDir, `${fetchCommitSha}.json`), snapshot)
    writeJsonAtomic(join(this.catalogCacheDir, 'latest.json'), snapshot)
    this.lastCatalog = snapshot
    return snapshot
  }

  search({ query = '', kind, selectable } = {}) {
    const snapshot = this.lastCatalog ?? this.fetchCatalog()
    const q = String(query).toLowerCase().trim()
    const matches = snapshot.catalog.entries.filter((entry) => {
      if (kind && entry.kind !== kind) return false
      if (selectable !== undefined && entry.selectable !== selectable) return false
      if (!q) return true
      return `${entry.entryId} ${entry.name} ${entry.summary} ${(entry.problemDomains || []).join(' ')}`.toLowerCase().includes(q)
    })
    return { snapshot, matches }
  }

  cachePath(entryId, sha) {
    if (!ENTRY_ID_RE.test(entryId) || !SHA_RE.test(sha)) fail('unsafe_cache_key', 'Entry cache key is invalid')
    return join(this.entryCacheDir, `${entryId}@${sha}`)
  }

  verifyCachedEntry(entryId, sha, { snapshot = this.lastCatalog } = {}) {
    const localPath = this.cachePath(entryId, sha)
    const metadataPath = join(localPath, 'verification.json')
    if (!existsSync(metadataPath)) fail('offline_verification_missing', `Verification record is missing for ${entryId}@${sha}`)
    const metadata = readJson(metadataPath, 'entry verification record')
    if (metadata.entryId !== entryId || metadata.entryCommitSha !== sha || metadata.catalogCommitSha !== sha || !snapshot || snapshot.catalogCommitSha !== sha) fail('entry_catalog_sha_mismatch', `Entry cache is not bound to the current catalog commit: ${entryId}@${sha}`)
    const entryPath = join(localPath, 'entry.json')
    if (!existsSync(entryPath)) fail('offline_entry_missing', `Cached entry metadata is missing: ${entryId}@${sha}`)
    const entry = readJson(entryPath, 'cached entry')
    validateEntryDocument(entry, `cached ${entryId}`)
    if (sha256File(entryPath) !== metadata.entryJsonSha256) fail('cache_integrity_failure', `Cached entry metadata was tampered: ${entryId}@${sha}`)
    const payloadHashes = verifyEntryPayload(entry, localPath)
    if (JSON.stringify(payloadHashes) !== JSON.stringify(metadata.payloadHashes)) fail('cache_integrity_failure', `Cached payload evidence was tampered: ${entryId}@${sha}`)
    const row = snapshot.catalog.entries.find((candidate) => candidate.entryId === entryId)
    if (!row || JSON.stringify(projectCatalogEntry(entry)) !== JSON.stringify(row)) fail('catalog_entry_mismatch', `Cached entry metadata does not match the catalog row: ${entryId}`)
    return { entryId, fetchCommitSha: sha, localPath, entryJson: entry, metadata, cacheStatus: 'verified', stale: Boolean(snapshot.stale) }
  }

  fetchEntry(entryId, commitSha) {
    if (!ENTRY_ID_RE.test(entryId)) fail('invalid_entry_id', `Invalid entryId: ${entryId}`)
    const snapshot = this.lastCatalog ?? this.fetchCatalog()
    const sha = commitSha ?? snapshot.catalogCommitSha
    if (sha !== snapshot.catalogCommitSha) fail('entry_catalog_sha_mismatch', `Entry ${entryId} must be fetched at catalog commit ${snapshot.catalogCommitSha}`, { catalogCommitSha: snapshot.catalogCommitSha, requested: sha })
    const localPath = this.cachePath(entryId, sha)
    if (existsSync(localPath)) return this.verifyCachedEntry(entryId, sha, { snapshot })
    if (this.offline) fail('offline_verification_missing', `Offline verification record is missing for ${entryId}@${sha}`)
    const row = snapshot.catalog.entries.find((candidate) => candidate.entryId === entryId)
    if (!row) fail('entry_not_found', `Entry not found in catalog: ${entryId}`)
    this.ensureMirror()
    try { run('git', ['-C', this.mirrorDir, 'cat-file', '-e', `${sha}^{commit}`]) } catch { fail('entry_commit_unavailable', `Authority cannot provide immutable commit ${sha}`) }
    run('git', ['-C', this.mirrorDir, 'sparse-checkout', 'set', `entries/${entryId}`])
    rmSync(join(this.mirrorDir, 'entries', entryId), { recursive: true, force: true })
    run('git', ['-C', this.mirrorDir, 'checkout', sha, '--', `entries/${entryId}`])
    const source = join(this.mirrorDir, 'entries', entryId)
    if (!existsSync(source) || !lstatSync(source).isDirectory()) fail('entry_not_found', `Entry payload is missing: ${entryId}@${sha}`)
    ensureDir(localPath)
    cpSync(source, localPath, { recursive: true, errorOnExist: false })
    const entry = readJson(join(localPath, 'entry.json'), 'authority entry')
    validateEntryDocument(entry, `entry ${entryId}`)
    if (entry.entryId !== entryId || JSON.stringify(projectCatalogEntry(entry)) !== JSON.stringify(row)) fail('catalog_entry_mismatch', `Entry does not match its catalog row: ${entryId}`)
    const payloadHashes = verifyEntryPayload(entry, localPath)
    const metadata = { schemaVersion: 1, entryId, entryCommitSha: sha, catalogCommitSha: sha, catalogEntriesSha256: snapshot.catalog.entriesSha256, entryJsonSha256: sha256File(join(localPath, 'entry.json')), payloadHashes, verified: true }
    writeJsonAtomic(join(localPath, 'verification.json'), metadata)
    return this.verifyCachedEntry(entryId, sha, { snapshot })
  }

  selectEntry(entryId, options = {}) {
    const fetched = this.fetchEntry(entryId, options.commitSha)
    if (!fetched.entryJson.selectable || !['usable', 'deprecated'].includes(fetched.entryJson.state)) fail('entry_not_selectable', `Entry is not selectable: ${entryId}`, { state: fetched.entryJson.state, selectable: fetched.entryJson.selectable })
    const compatibility = compatibilityReport(fetched.entryJson, { consumerRoot: options.consumerRoot ?? this.consumerRoot, runtime: options.runtime, nodeVersion: options.nodeVersion, frameworks: options.frameworks, dependencies: options.dependencies, services: options.services })
    if (!compatibility.ok) fail('entry_incompatible', `Entry is incompatible with the consumer: ${entryId}`, compatibility)
    const provenance = this.recordProvenance(fetched, { selected: true, compatibility })
    return { ...fetched, compatibility, provenance }
  }

  recordProvenance(fetched, { selected = false, compatibility = null } = {}) {
    const report = { schemaVersion: 1, consumerId: this.consumerId, runId: this.runId, repoUrl: this.repoUrl, branch: this.baseBranch, catalogCommitSha: fetched.metadata?.catalogCommitSha ?? fetched.fetchCommitSha, entryId: fetched.entryId, entryCommitSha: fetched.fetchCommitSha, catalogEntriesSha256: fetched.metadata?.catalogEntriesSha256 ?? this.lastCatalog?.catalog.entriesSha256, entryJsonSha256: fetched.metadata?.entryJsonSha256, payloadHashes: fetched.metadata?.payloadHashes, state: fetched.entryJson.state, selectable: fetched.entryJson.selectable, selected, compatibility, cacheStatus: fetched.cacheStatus, stale: fetched.stale }
    const path = join(this.provenanceDir, `${fetched.entryId}@${fetched.fetchCommitSha}.json`)
    writeJsonAtomic(path, report)
    return { path, ...report }
  }

  report(entryId) {
    const snapshot = this.lastCatalog ?? this.fetchCatalog()
    if (!entryId) return { snapshot, cacheRoot: this.cacheRoot, consumerId: this.consumerId, runId: this.runId }
    const fetched = this.fetchEntry(entryId)
    const provenancePath = join(this.provenanceDir, `${entryId}@${fetched.fetchCommitSha}.json`)
    return { snapshot, entry: fetched, provenance: existsSync(provenancePath) ? readJson(provenancePath, 'provenance report') : null }
  }

  prepareContribution(bundlePath) {
    const abs = resolve(bundlePath)
    if (!pathInside(abs, abs) || !existsSync(join(abs, 'entry.json'))) fail('invalid_contribution', 'Contribution bundle must contain entry.json')
    const entry = readJson(join(abs, 'entry.json'), 'contribution entry')
    validateEntryDocument(entry, 'contribution entry')
    return { bundlePath: abs, entryId: entry.entryId }
  }

  validateContribution(bundlePath) {
    try {
      const prepared = this.prepareContribution(bundlePath)
      const entryPath = join(prepared.bundlePath, 'entry.json')
      const entry = readJson(entryPath, 'contribution entry')
      const payloadHashes = verifyEntryPayload(entry, prepared.bundlePath)
      return { ok: true, entryId: prepared.entryId, payloadHashes }
    } catch (error) {
      return { ok: false, errors: [{ code: error.code ?? 'invalid_contribution', message: error.message }] }
    }
  }

  publishContribution(bundlePath) {
    const validation = this.validateContribution(bundlePath)
    if (!validation.ok) return { status: 'publication_rejected', published: false, validation }
    if (process.env.LINKTREND_SHARED_LIBRARY_PUBLISH !== '1') return { status: 'publication_disabled', published: false, detail: `Contribution ${validation.entryId} is valid locally; publication is disabled.` }
    if (!process.env.LINKTREND_SHARED_LIBRARY_PUBLISH_AUTHORITY) return { status: 'publication_missing_authority', published: false, detail: 'Publication was requested but no approved publication authority is available.' }
    return { status: 'publication_pending', published: false, detail: 'Contribution is valid and authority is present; Librarian PR creation remains an external governed action.' }
  }
}

function printJson(value) { console.log(JSON.stringify(value, null, 2)) }

function option(args, name) {
  const index = args.indexOf(name)
  return index >= 0 ? args[index + 1] : undefined
}

function main(argv) {
  const [command, ...args] = argv
  const client = new LibraryClient()
  if (command === 'sync') return printJson(client.fetchCatalog())
  if (command === 'search') return printJson(client.search({ query: option(args, '--query') ?? '', kind: option(args, '--kind'), selectable: option(args, '--selectable') === undefined ? undefined : option(args, '--selectable') === 'true' }))
  if (command === 'show') return printJson(client.fetchEntry(option(args, '--entry') ?? fail('argument_required', '--entry required')))
  if (command === 'select') return printJson(client.selectEntry(option(args, '--entry') ?? fail('argument_required', '--entry required')))
  if (command === 'verify-cache') return printJson(client.verifyCachedEntry(option(args, '--entry') ?? fail('argument_required', '--entry required'), client.fetchCatalog().catalogCommitSha))
  if (command === 'report') return printJson(client.report(option(args, '--entry')))
  if (command === 'prepare-contribution') return printJson(client.prepareContribution(option(args, '--bundle') ?? fail('argument_required', '--bundle required')))
  if (command === 'validate-contribution') {
    const result = client.validateContribution(option(args, '--bundle') ?? fail('argument_required', '--bundle required'))
    printJson(result)
    if (!result.ok) process.exitCode = 1
    return
  }
  if (command === 'publish-contribution') return printJson(client.publishContribution(option(args, '--bundle') ?? fail('argument_required', '--bundle required')))
  if (!command || command === 'help') return console.log('Usage: node library-client.mjs <sync|search|show|select|verify-cache|report|prepare-contribution|validate-contribution|publish-contribution>')
  fail('unknown_command', `Unknown command: ${command}`)
}

// Node can preserve an archive/extraction spelling in argv[1] that is not
// byte-identical to the decoded module URL (notably on paths containing
// spaces). The suffix check keeps direct CLI execution reliable while still
// allowing the client to be imported by tests and other commands.
const isMain = Boolean(process.argv[1] && (process.argv[1].endsWith('/library-client.mjs') || process.argv[1].endsWith('\\library-client.mjs')))
if (isMain) {
  try { main(process.argv.slice(2)) } catch (error) {
    console.error(error.message ?? error)
    process.exitCode = 1
  }
}
