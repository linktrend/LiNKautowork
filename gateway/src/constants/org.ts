// Canonical internal organization identity.
//
// Under the shared platform org model (docs/adr/0001), LiNKautowork's
// tenant-scoped concept is an organization in platform.organizations, and this
// value is what lands in the org_id column of the lautowork control tables.
// The identifiers are named for what the value now IS (an org id/slug); only
// the VALUE below is load-bearing and MUST NOT change — it remains the
// canonical internal-org id used across the gateway and deploy env contract.
export const CANONICAL_INTERNAL_ORG_UUID = '00000000-0000-0000-0000-000000000001';
export const INTERNAL_ORG_SLUG = 'linktrend_internal';
