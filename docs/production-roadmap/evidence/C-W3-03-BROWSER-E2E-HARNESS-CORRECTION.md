# C-W3-03 — Real-browser E2E harness correction

## Defect and correction

The local Chrome browser proof had two harness defects. Its incident-heading
locator matched both the page heading and the confirmation-dialog heading, so
Playwright raised a strict-locator failure after the operator page loaded. Its
cleanup also had no bounded diagnostics, making an interrupted or slow browser
shutdown appear to be a hung test.

The harness now uses an exact page-heading assertion and records bounded,
named steps for browser launch, context/session setup, page load, each user
interaction, and shutdown. It reports browser console messages, page errors,
failed requests, and Product API response status codes. Browser launch is
bounded at 20 seconds; individual proof steps are bounded at 8 seconds; cleanup
is bounded at 15 seconds to allow Chrome to settle child processes. Servers
close all active connections during finalisation.

## Regression proof

Two consecutive local executions of `npm --prefix apps/web run test:browser`
completed successfully against the system Chrome executable at
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. After each
run, process inspection found no LiNKautowork browser-E2E process, Chrome
process, or local server remaining.

Each successful run proves, through the actual compiled client and operator
console, that:

- the mobile client shell is accessible and completes public/list/portal plus
  order (201), subscription (201), and provisioning-request (202) calls;
- credential-like input fields are absent and the 390px responsive shell is
  rendered;
- a client-member operator-console session receives a real 403 and no action
  controls;
- an operator can open the acknowledgement dialog, record a reason, confirm
  the scope, submit the incident action, and receive an audited receipt;
- unsafe incident text is rendered as `[redacted]`; and
- promotion remains separately gated for a non-approver while provisioning is
  visible as a distinct operational area.

This is local integration proof only. It does not contact a VPS, live identity
issuer, payment provider, GSM, Supabase Cloud, or production n8n instance.
