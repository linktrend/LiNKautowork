/**
 * Frozen consumer pins for the five LiNK providers.
 *
 * Each pin is the GitHub `development` tip of that provider repository at
 * WP-I6-S0 freeze time (read-only `gh api repos/linktrend/<Provider>/commits/development`).
 * Local sibling checkout HEADs are not pins. Live `HEAD` / `latest` is not a pin.
 *
 * This module is inventory only. It has no transport, credentials, Git write,
 * Ledger, or Gate mutation APIs.
 */

const GIT_SHA = /^[a-f0-9]{40}$/

/** @typedef {{ repository: string, commit: string, tree: string }} FrozenProviderPin */

/**
 * Pin authority. Sibling clones and other local checkouts must not replace these
 * identities, even when they are ahead of `origin/development`.
 */
export const PIN_AUTHORITY = Object.freeze({
  source: 'github_development_tip',
  owner: 'linktrend',
  ref: 'development',
  frozenOn: '2026-08-17',
  siblingCheckoutHeadsAreNotPins: true,
})

export const FROZEN_PROVIDER_KEYS = Object.freeze([
  'platform',
  'libraries',
  'brain',
  'skills',
  'autowork',
])

/**
 * @param {string} repository
 * @param {string} commit
 * @param {string} tree
 * @returns {FrozenProviderPin}
 */
function pin(repository, commit, tree) {
  if (typeof repository !== 'string' || !repository.startsWith('linktrend/')) {
    throw new Error('provider pin repository must be a linktrend GitHub identity')
  }
  if (!GIT_SHA.test(commit) || !GIT_SHA.test(tree)) {
    throw new Error(`provider pin ${repository} must use 40-character lowercase git SHAs`)
  }
  return Object.freeze({ repository, commit, tree })
}

export const FROZEN_PROVIDERS = Object.freeze({
  platform: pin(
    'linktrend/LiNKplatform',
    '2d5f37ef6b8e40ad47305adab47613d915967c1b',
    '90b51726f7a77e4620151a463a10cfc3d2007c88',
  ),
  libraries: pin(
    'linktrend/LiNKlibraries',
    '5901d111309543ed0839938d7217475e5d4b8ac4',
    '185d7cf714777d60a2d01a4881bf1a11bc5018d9',
  ),
  brain: pin(
    'linktrend/LiNKbrain',
    '77af7d02a76e6a8877d59fbd3d3e917ac6e830c5',
    '0cae42d612342f5e52c7e2e0e76cb6fc2f6d81f3',
  ),
  skills: pin(
    'linktrend/LiNKskills',
    '0d6bf34546f89c9beb7f05483a3ed4deeb3a5a67',
    '6c36e6c98f90e55d957fba781327b1b0ef90860a',
  ),
  autowork: pin(
    'linktrend/LiNKautowork',
    '9caab9aa33de5f96e33d67d880f2934dc6fd9fef',
    '5f306d674780a5a26048017f916da6048d71e7a5',
  ),
})

if (Object.keys(FROZEN_PROVIDERS).length !== FROZEN_PROVIDER_KEYS.length) {
  throw new Error('FROZEN_PROVIDERS must contain exactly the five named providers')
}
for (const key of FROZEN_PROVIDER_KEYS) {
  if (!FROZEN_PROVIDERS[key]) {
    throw new Error(`FROZEN_PROVIDERS missing ${key}`)
  }
}
