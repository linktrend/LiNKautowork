import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { LibraryClient, LibraryClientError } from '../library-client.mjs'
import { validSpdxExpression } from '../vendor/spdx-expression-validate.mjs'

const sha256 = (value) => createHash('sha256').update(value).digest('hex')
const json = (value) => `${JSON.stringify(value, null, 2)}\n`

function git(cwd, args) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
}

function entry({ id, state = 'usable', selectable = true, framework = 'react', nodeRequirement = '>=20', dependencyVersion = '19.1.1', operatingSystems }) {
  const readme = `# ${id}\n\nA verified test component.\n`
  return {
    schemaVersion: 2,
    entryId: id,
    kind: 'vetted_oss',
    name: id,
    summary: 'A verified reusable library entry for consumer conformance tests.',
    problemDomains: ['testing'],
    tags: ['test'],
    languages: ['javascript'],
    frameworks: framework ? [framework] : [],
    state,
    contentMode: state === 'metadata_only' ? 'documentation' : 'executable',
    selectable,
    compatibility: { node: nodeRequirement, runtimes: ['node'], ...(operatingSystems ? { operatingSystems } : {}) },
    dependencies: { packages: state === 'metadata_only' ? [] : [{ name: 'react', version: dependencyVersion, ecosystem: 'npm' }], services: [] },
    ...(state === 'metadata_only' ? {} : { testContract: { runner: 'node:test', files: ['tests/example.test.mjs'], timeoutMs: 30000 } }),
    license: { spdx: 'MIT', redistributionAllowed: true },
    securityReview: { reviewedAt: '2026-08-04T00:00:00.000Z', reviewedBy: 'test', notes: 'Safe local fixture.' },
    usage: { howToUse: 'Import the verified fixture into a test consumer.' },
    integrationNotes: 'Use only as a disposable conformance fixture and verify the exact source commit.',
    gotchas: ['Do not use this fixture as a production Starter Kit.'],
    provenance: { sourceSystem: 'manual', sourceRevisionSha: 'a'.repeat(40), contributedAt: '2026-08-04T00:00:00.000Z', sourceUrl: 'https://example.com/source', versionOrRange: '1.0.0' },
    files: state === 'metadata_only'
      ? [{ path: 'README.md', sha256: sha256(readme) }]
      : [{ path: 'README.md', sha256: sha256(readme) }, { path: 'assets/example.js', sha256: sha256('export const example = true\n') }, { path: 'tests/example.test.mjs', sha256: sha256('import { test } from "node:test"\ntest("fixture", () => {})\n') }],
  }
}

function createAuthority(extraEntries = []) {
  const root = mkdtempSync(join(tmpdir(), 'linklibraries-authority-'))
  mkdirSync(join(root, 'entries', 'hello-world'), { recursive: true })
  mkdirSync(join(root, 'entries', 'historical-note'), { recursive: true })
  mkdirSync(join(root, 'indexes'), { recursive: true })
  const hello = entry({ id: 'hello-world' })
  const historical = entry({ id: 'historical-note', state: 'metadata_only', selectable: false, framework: 'react' })
  for (const item of [hello, historical, ...extraEntries]) {
    const path = join(root, 'entries', item.entryId)
    mkdirSync(path, { recursive: true })
    const readme = `# ${item.entryId}\n\nA verified test component.\n`
    writeFileSync(join(path, 'entry.json'), json(item))
    writeFileSync(join(path, 'README.md'), readme)
    if (item.state !== 'metadata_only') {
      mkdirSync(join(path, 'assets'))
      mkdirSync(join(path, 'tests'))
      writeFileSync(join(path, 'assets', 'example.js'), 'export const example = true\n')
      writeFileSync(join(path, 'tests', 'example.test.mjs'), 'import { test } from "node:test"\ntest("fixture", () => {})\n')
    }
  }
  const project = (item) => {
    const row = {}
    for (const key of ['entryId', 'kind', 'name', 'summary', 'problemDomains', 'tags', 'languages', 'frameworks', 'state', 'contentMode', 'selectable', 'compatibility', 'dependencies']) row[key] = item[key]
    row.path = `entries/${item.entryId}`
    return row
  }
  const rows = [hello, historical, ...extraEntries].map(project).sort((a, b) => a.entryId.localeCompare(b.entryId))
  writeFileSync(join(root, 'indexes', 'catalog.json'), json({ schemaVersion: 2, entriesSha256: sha256(JSON.stringify(rows)), entries: rows }))
  git(root, ['init', '-b', 'development'])
  git(root, ['config', 'user.email', 'library-test@example.com'])
  git(root, ['config', 'user.name', 'Library Test'])
  git(root, ['add', '.'])
  git(root, ['commit', '-m', 'fixture authority'])
  return { root, sha: git(root, ['rev-parse', 'HEAD']), hello, historical }
}

function client(authority, cacheRoot, options = {}) {
  return new LibraryClient({ repoUrl: authority.root, baseBranch: 'development', cacheRoot, runId: 'test-run', consumerId: 'test-consumer', ...options })
}

function writeBundle(root, item) {
  mkdirSync(root, { recursive: true })
  writeFileSync(join(root, 'entry.json'), json(item))
  const readme = `# ${item.entryId}\n\nA verified test component.\n`
  writeFileSync(join(root, 'README.md'), readme)
  if (item.files.some((file) => file.path === 'assets/example.js')) {
    mkdirSync(join(root, 'assets'), { recursive: true })
    writeFileSync(join(root, 'assets', 'example.js'), 'export const example = true\n')
  }
  if (item.files.some((file) => file.path === 'tests/example.test.mjs')) {
    mkdirSync(join(root, 'tests'), { recursive: true })
    writeFileSync(join(root, 'tests', 'example.test.mjs'), 'import { test } from "node:test"\ntest("fixture", () => {})\n')
  }
}

test('binds catalog and entry to one immutable SHA and records provenance', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-cache-'))
  try {
    const result = client(authority, cache).fetchEntry('hello-world')
    assert.equal(result.fetchCommitSha, authority.sha)
    assert.equal(result.entryJson.entryId, 'hello-world')
    assert.equal(result.metadata.catalogCommitSha, authority.sha)
    assert.deepEqual(Object.keys(result.metadata.payloadHashes), ['assets/example.js', 'README.md', 'tests/example.test.mjs'])
    const selected = client(authority, cache, { consumerRoot: cache }).selectEntry('hello-world', { dependencies: { react: '19.1.1' }, frameworks: ['react'] })
    assert.equal(selected.compatibility.ok, true)
    assert.equal(readFileSync(join(cache, 'provenance', `hello-world@${authority.sha}.json`), 'utf8').includes(authority.sha), true)
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('rejects mismatched catalog/entry SHA and traversal identifiers', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-cache-'))
  try {
    const instance = client(authority, cache)
    instance.fetchCatalog()
    assert.throws(() => instance.fetchEntry('hello-world', '0'.repeat(40)), (error) => error instanceof LibraryClientError && error.code === 'entry_catalog_sha_mismatch')
    assert.throws(() => instance.fetchEntry('../escape'), (error) => error instanceof LibraryClientError && error.code === 'invalid_entry_id')
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('rejects metadata-only selection and incompatible dependencies', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-cache-'))
  try {
    const instance = client(authority, cache)
    assert.throws(() => instance.selectEntry('historical-note'), (error) => error.code === 'entry_not_selectable')
    assert.throws(() => instance.selectEntry('hello-world', { nodeVersion: '19.0.0', frameworks: ['vue'], dependencies: {} }), (error) => error.code === 'entry_incompatible' && error.details.errors.length >= 2)
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('accepts catalog OS constraints and rejects an incompatible consumer OS', () => {
  const constrained = entry({ id: 'linux-only', operatingSystems: ['linux'] })
  const authority = createAuthority([constrained])
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-os-'))
  try {
    const instance = client(authority, cache)
    const selected = instance.selectEntry('linux-only', { operatingSystem: 'linux', dependencies: { react: '19.1.1' }, frameworks: ['react'] })
    assert.equal(selected.compatibility.operatingSystem, 'linux')
    assert.throws(
      () => instance.selectEntry('linux-only', { operatingSystem: 'darwin', dependencies: { react: '19.1.1' }, frameworks: ['react'] }),
      (error) => error.code === 'entry_incompatible' && error.details.errors.some((item) => item.code === 'operating_system_incompatible'),
    )
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('executes packaged v2 schema conditionals, additionalProperties, formats, and valid cases', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-schema-'))
  const valid = entry({ id: 'schema-valid' })
  valid.provenance = {
    ...valid.provenance,
    pullRequestNumber: 42,
    pullRequestUrl: 'https://github.com/linktrend/LiNKlibraries/pull/42',
  }
  const validBundle = join(cache, 'valid')
  writeBundle(validBundle, valid)
  try {
    assert.equal(client(authority, cache).validateContribution(validBundle).ok, true)

    const deprecatedMissingMetadata = { ...entry({ id: 'deprecated-missing', state: 'deprecated', selectable: true }) }
    delete deprecatedMissingMetadata.deprecation
    writeBundle(join(cache, 'deprecated'), deprecatedMissingMetadata)
    const deprecatedResult = client(authority, cache).validateContribution(join(cache, 'deprecated'))
    assert.equal(deprecatedResult.ok, false)
    assert.equal(deprecatedResult.errors[0].code, 'schema_validation_failed')

    const extraProperty = { ...valid, extraProperty: true }
    writeBundle(join(cache, 'extra'), extraProperty)
    const extraResult = client(authority, cache).validateContribution(join(cache, 'extra'))
    assert.equal(extraResult.ok, false)
    assert.equal(extraResult.errors[0].code, 'schema_validation_failed')

    const invalidFormat = { ...valid, securityReview: { ...valid.securityReview, reviewedAt: 'not-a-date-time' } }
    writeBundle(join(cache, 'format'), invalidFormat)
    const formatResult = client(authority, cache).validateContribution(join(cache, 'format'))
    assert.equal(formatResult.ok, false)
    assert.equal(formatResult.errors[0].code, 'schema_validation_failed')
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('matches locked LiNKlibraries SPDX current, deprecated, and exception sets', () => {
  const vendor = fileURLToPath(new URL('../vendor/', import.meta.url))
  const load = (name) => JSON.parse(readFileSync(join(vendor, name), 'utf8'))
  const current = load('spdx-license-ids.json')
  const deprecated = load('spdx-license-ids-deprecated.json')
  const exceptions = load('spdx-exceptions.json')

  for (const license of [...current, ...deprecated]) {
    assert.equal(validSpdxExpression(license), true, `authority license: ${license}`)
    assert.equal(validSpdxExpression(`${license}+`), true, `authority plus: ${license}`)
    assert.equal(validSpdxExpression(`${license} WITH ${exceptions[0]}`), true, `authority WITH: ${license}`)
  }
  for (const exception of exceptions) {
    assert.equal(validSpdxExpression(`MIT WITH ${exception}`), true, `authority exception: ${exception}`)
  }

  for (const expression of [
    '(MIT OR Apache-2.0)',
    '(MIT AND (GPL-2.0+ OR BSD-3-Clause))',
    'LicenseRef-23',
    'LicenseRef-MIT-Style-1',
    'DocumentRef-spdx-tool-1.2:LicenseRef-MIT-Style-2',
  ]) assert.equal(validSpdxExpression(expression), true, `authority grammar: ${expression}`)

  for (const expression of [
    'Definitely-Not-A-License',
    'MIT WITH Definitely-Not-An-Exception',
    'Definitely-Not-A-License WITH Bison-exception-2.2',
    'Apache 2',
    'MIT ',
    ' MIT',
    'MIT  AND  Apache-2.0',
    'MIT AND',
    '(MIT OR Apache-2.0',
  ]) assert.equal(validSpdxExpression(expression), false, `authority rejection: ${expression}`)
})

test('accepts and rejects schema-valid and invalid provenance fields consistently', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-provenance-'))
  try {
    const valid = entry({ id: 'provenance-valid' })
    valid.provenance = {
      ...valid.provenance,
      sourceUrl: 'https://example.com/source',
      versionOrRange: '1.0.0',
      productRunId: 'run-42',
      pullRequestNumber: 42,
      pullRequestUrl: 'https://github.com/linktrend/LiNKlibraries/pull/42',
    }
    const validPath = join(cache, 'valid')
    writeBundle(validPath, valid)
    assert.equal(client(authority, cache).validateContribution(validPath).ok, true)

    for (const [field, value] of [
      ['pullRequestUrl', 'not-a-uri'],
      ['sourceUrl', 'not-a-uri'],
      ['pullRequestNumber', 0],
      ['productRunId', ''],
    ]) {
      const invalid = entry({ id: `provenance-invalid-${field.toLowerCase()}` })
      invalid.provenance = { ...invalid.provenance, [field]: value }
      const path = join(cache, `invalid-${field}`)
      writeBundle(path, invalid)
      const result = client(authority, cache).validateContribution(path)
      assert.equal(result.ok, false, `invalid provenance field: ${field}`)
      assert.equal(result.errors[0].code, 'schema_validation_failed')
    }
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('rejects schema-invalid deprecated selectable entries before selection', () => {
  const broken = entry({ id: 'deprecated-selectable', state: 'deprecated', selectable: true })
  delete broken.deprecation
  const authority = createAuthority([broken])
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-deprecation-'))
  const selectionCache = mkdtempSync(join(tmpdir(), 'linklibraries-deprecation-select-'))
  try {
    assert.throws(() => client(authority, cache).fetchEntry(broken.entryId), (error) => error.code === 'schema_validation_failed')
    assert.throws(() => client(authority, selectionCache).selectEntry(broken.entryId), (error) => error.code === 'schema_validation_failed')
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }); rmSync(selectionCache, { recursive: true, force: true }) }
})

test('enforces exact, caret, tilde, comparator conjunction, malformed, and unsupported npm ranges', () => {
  const ranges = [
    entry({ id: 'range-exact', dependencyVersion: '20.2.3' }),
    entry({ id: 'range-caret', dependencyVersion: '^20.0.0', nodeRequirement: '^20.0.0' }),
    entry({ id: 'range-tilde', dependencyVersion: '~20.2.0' }),
    entry({ id: 'range-comparator', dependencyVersion: '>=20.0.0 <21.0.0' }),
    entry({ id: 'range-malformed', dependencyVersion: '>=20.0.0 <' }),
    entry({ id: 'range-unsupported', dependencyVersion: '*' }),
  ]
  const authority = createAuthority(ranges)
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-semver-'))
  try {
    const instance = client(authority, cache)
    for (const id of ['range-exact', 'range-caret', 'range-tilde', 'range-comparator']) {
      assert.doesNotThrow(() => instance.selectEntry(id, { nodeVersion: '20.2.3', dependencies: { react: '^20.1.0' } }))
    }
    assert.doesNotThrow(() => instance.selectEntry('range-caret', { nodeVersion: '20.2.3', dependencies: { react: '>=20.0.0' } }))
    assert.doesNotThrow(() => instance.selectEntry('range-tilde', { nodeVersion: '20.2.3', dependencies: { react: '>=20.2.0' } }))
    assert.throws(() => instance.selectEntry('range-caret', { nodeVersion: '20.2.3', dependencies: { react: '>=21.0.0' } }), (error) => error.code === 'entry_incompatible' && error.details.errors.some((item) => item.code === 'dependency_incompatible'))
    assert.throws(() => instance.selectEntry('range-caret', { nodeVersion: '20.2.3', dependencies: { react: '19.1.1' } }), (error) => error.code === 'entry_incompatible' && error.details.errors.some((item) => item.code === 'dependency_incompatible'))
    assert.throws(() => instance.selectEntry('range-malformed', { nodeVersion: '20.2.3', dependencies: { react: '20.2.3' } }), (error) => error.code === 'entry_incompatible' && error.details.errors.some((item) => item.code === 'dependency_range_malformed'))
    assert.throws(() => instance.selectEntry('range-unsupported', { nodeVersion: '20.2.3', dependencies: { react: '20.2.3' } }), (error) => error.code === 'entry_incompatible' && error.details.errors.some((item) => item.code === 'dependency_range_unsupported'))
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('fails closed on tampered cache and only reuses revalidated offline evidence', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-cache-'))
  try {
    const online = client(authority, cache)
    online.fetchEntry('hello-world')
    writeFileSync(join(cache, 'entries', `hello-world@${authority.sha}`, 'assets', 'example.js'), 'tampered\n')
    assert.throws(() => client(authority, cache).fetchEntry('hello-world'), (error) => error.code === 'cache_integrity_failure' || error.code === 'payload_sha256_mismatch')
    rmSync(join(cache, 'entries', `hello-world@${authority.sha}`), { recursive: true, force: true })
    online.fetchEntry('hello-world')
    const offline = client(authority, cache, { offline: true })
    const reused = offline.fetchEntry('hello-world')
    assert.equal(reused.stale, true)
    rmSync(join(cache, 'entries', `hello-world@${authority.sha}`, 'verification.json'))
    assert.throws(() => offline.fetchEntry('hello-world'), (error) => error.code === 'offline_verification_missing')
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('repairs an incomplete online cache entry but preserves offline fail-closed behavior', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-incomplete-cache-'))
  const partial = join(cache, 'entries', `hello-world@${authority.sha}`)
  try {
    mkdirSync(partial, { recursive: true })
    writeFileSync(join(partial, 'partial-download'), 'unverified\n')
    const repaired = client(authority, cache).fetchEntry('hello-world')
    assert.equal(repaired.cacheStatus, 'verified')
    assert.equal(existsSync(join(partial, 'partial-download')), false)
    rmSync(join(partial, 'verification.json'))
    assert.throws(() => client(authority, cache, { offline: true }).fetchEntry('hello-world'), (error) => error.code === 'offline_verification_missing')
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('CLI select discovers package compatibility from the consumer working directory', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-cli-select-'))
  const consumer = join(cache, 'consumer')
  mkdirSync(consumer)
  writeFileSync(join(consumer, 'package.json'), json({ dependencies: { react: '19.1.1' } }))
  try {
    const output = execFileSync(
      process.execPath,
      [fileURLToPath(new URL('../library-client.mjs', import.meta.url)), 'select', '--entry', 'hello-world'],
      {
        cwd: consumer,
        encoding: 'utf8',
        env: {
          ...process.env,
          LINKTREND_SHARED_LIBRARY_REPO_URL: authority.root,
          LINKTREND_SHARED_LIBRARY_CHECKOUT: join(cache, 'cli-cache'),
        },
      },
    )
    assert.equal(JSON.parse(output).compatibility.ok, true)
  } finally { rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true }) }
})

test('reports truthful publication-disabled and missing-authority outcomes', () => {
  const authority = createAuthority()
  const cache = mkdtempSync(join(tmpdir(), 'linklibraries-cache-'))
  const bundle = join(cache, 'bundle')
  mkdirSync(join(bundle, 'assets'), { recursive: true })
  const readme = '# contribution\n\nA verified test component.\n'
  writeFileSync(join(bundle, 'README.md'), readme)
  const contribution = entry({ id: 'contribution', framework: null })
  contribution.contentMode = 'documentation'
  delete contribution.testContract
  contribution.files = [{ path: 'README.md', sha256: sha256(readme) }]
  contribution.dependencies = { packages: [], services: [] }
  writeFileSync(join(bundle, 'entry.json'), json(contribution))
  const oldPublish = process.env.LINKTREND_SHARED_LIBRARY_PUBLISH
  const oldAuthority = process.env.LINKTREND_SHARED_LIBRARY_PUBLISH_AUTHORITY
  try {
    delete process.env.LINKTREND_SHARED_LIBRARY_PUBLISH
    delete process.env.LINKTREND_SHARED_LIBRARY_PUBLISH_AUTHORITY
    assert.equal(client(authority, cache).publishContribution(bundle).status, 'publication_disabled')
    process.env.LINKTREND_SHARED_LIBRARY_PUBLISH = '1'
    assert.equal(client(authority, cache).publishContribution(bundle).status, 'publication_missing_authority')
  } finally {
    if (oldPublish === undefined) delete process.env.LINKTREND_SHARED_LIBRARY_PUBLISH
    else process.env.LINKTREND_SHARED_LIBRARY_PUBLISH = oldPublish
    if (oldAuthority === undefined) delete process.env.LINKTREND_SHARED_LIBRARY_PUBLISH_AUTHORITY
    else process.env.LINKTREND_SHARED_LIBRARY_PUBLISH_AUTHORITY = oldAuthority
    rmSync(authority.root, { recursive: true, force: true }); rmSync(cache, { recursive: true, force: true })
  }
})

test('executes the physical client as a CLI from a path containing spaces', () => {
  const output = execFileSync(process.execPath, [fileURLToPath(new URL('../library-client.mjs', import.meta.url)), 'help'], { encoding: 'utf8' })
  assert.match(output, /sync\|search\|show\|select/)
})
