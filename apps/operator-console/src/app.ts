import { isOperatorActionAllowed, ProductApiClient, type ApiResult, type OperatorAction, type OperatorResource, type ProductApiTransport, type SafeRecord } from './api.js';
import { actionAvailability, routeFor, screens, type ConsoleActor, type Screen } from './console.js';
import { operatorRuntimeConfig, operatorSession, startOperatorSignIn, type OperatorSession } from './platform-auth.js';

const idempotencyKey = () => crypto.randomUUID();
function transport(session: OperatorSession, productApiOrigin: string): ProductApiTransport {
  const request = async (path: string, init?: RequestInit) => {
    const base = productApiOrigin; const response = await fetch(new URL(path.replace(/^\//, ''), base.endsWith('/') ? base : `${base}/`), { ...init, headers: { accept: 'application/json', authorization: `Bearer ${session.accessToken}`, ...(init?.headers ?? {}) } });
    const body = await response.json() as unknown;
    if (body && typeof body === 'object' && !Array.isArray(body)) return { ...(body as Record<string, unknown>), correlationId: response.headers.get('x-correlation-id') ?? undefined, auditReference: response.headers.get('x-audit-reference') ?? undefined };
    return body;
  };
  return { get: (path) => request(path), post: (path, body) => request(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }) };
}
function text(value: unknown) { return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character] ?? character); }
const resourceFor: Record<Screen, OperatorResource> = { overview: 'health', catalogue: 'packages', instances: 'instances', provisioning: 'provisioning-jobs', executions: 'executions', incidents: 'incidents', certification: 'certification', releases: 'releases', deployments: 'deployments', maintenance: 'maintenance', librarian: 'librarian-candidates', 'audit-health': 'audit-evidence' };

function actionForRecord(selected: Screen, record: SafeRecord): OperatorAction | undefined {
  const state = record.state ?? record.status ?? '';
  if (selected === 'instances') return state === 'paused' ? 'resume' : ['active', 'ready'].includes(state) ? 'pause' : undefined;
  if (selected === 'provisioning') return ['requested', 'failed', 'awaiting_configuration'].includes(state) ? 'retry' : undefined;
  if (selected === 'incidents') return state === 'open' ? 'acknowledge' : ['acknowledged', 'investigating', 'mitigated'].includes(state) ? 'resolve' : undefined;
  if (selected === 'releases') return undefined;
  if (selected === 'deployments') return ['planned', 'ready'].includes(state) ? 'canary' : state === 'canary' ? 'promote' : state === 'active' ? 'rollback' : undefined;
  if (selected === 'librarian') return state === 'awaiting_review' ? 'approve' : state === 'approved' ? 'supersede' : ['proposed', 'validation_failed', 'ready_for_eval', 'eval_failed'].includes(state) ? 'reject' : undefined;
  if (selected === 'audit-health' || selected === 'overview' || selected === 'catalogue' || selected === 'executions') return undefined;
  return selected === 'certification' && record.status === 'eval_pending' ? 'approve' : selected === 'maintenance' ? (['open', 'investigating', 'awaiting_approval'].includes(state) ? 'retry' : 'resolve') : undefined;
}
function actionFor(selected: Screen, result: ApiResult<SafeRecord[]>): OperatorAction | undefined {
  return result.state === 'ready' ? result.value.map((record) => actionForRecord(selected, record)).find((action): action is OperatorAction => Boolean(action)) : undefined;
}

function renderUnavailable(message: string) { return `<main tabindex="-1"><h1>Operator sign-in required</h1><p>${text(message)}</p><p>This shell accepts an externally issued Platform session. It does not create, store, or display credentials.</p></main>`; }
function recordSummary(selected: Screen, records: SafeRecord[], session: ConsoleActor) {
  if (!records.length) return '<li>No current records.</li>';
  return records.map((record) => { const action = actionForRecord(selected, record); const availability = action ? actionAvailability(session, action) : undefined; return `<li data-record-id="${text(record.id)}"><strong>${text(record.id)}</strong> — ${text(record.status ?? record.state ?? 'recorded')}<span>${record.summary ? `: ${text(record.summary)}` : ''}</span>${record.evidenceRef ? `<small> Evidence: ${text(record.evidenceRef)}</small>` : ''}${action && availability ? `<button type="button" data-action="${action}" data-record-id="${text(record.id)}" ${availability.allowed ? '' : 'disabled'}>Review ${text(action)} scope</button>` : ''}</li>`; }).join('');
}
function render(session: OperatorSession, selected: Screen, result: ApiResult<SafeRecord[]>, feedback = '') {
  const navigation = screens.map((screen) => `<a href="#${screen.id}" ${selected === screen.id ? 'aria-current="page"' : ''}>${text(screen.title)}</a>`).join('');
  const screen = screens.find((item) => item.id === selected) ?? screens[0];
  if (!actionAvailability({ subject: session.subject, roles: session.roles }, 'rollback').allowed && !session.roles.includes('operator') && !session.roles.includes('approver')) return `<header><nav aria-label="Operator screens">${navigation}</nav></header>${renderUnavailable('Your current Platform role is not authorised for operations.')}`;
  const action = actionFor(selected, result); const availability = action ? actionAvailability({ subject: session.subject, roles: session.roles }, action) : undefined;
  const content = result.state === 'ready' ? `<ul aria-label="${text(screen.title)} records">${recordSummary(selected, result.value, { subject: session.subject, roles: session.roles })}</ul>` : `<p role="alert">${text(result.error.message)} Correlation: ${text(result.error.correlationId)}. No action was attempted.</p>`;
  return `<header><a href="#overview" class="brand">LiNKtrend operator console</a><nav aria-label="Operator screens">${navigation}</nav></header><main tabindex="-1"><p class="eyebrow">Authenticated operator workspace</p><h1>${text(screen.title)}</h1><p>${text(screen.summary)}</p>${feedback ? `<p role="status" class="feedback">${text(feedback)}</p>` : ''}<section aria-label="Current state"><h2>Current state</h2>${content}</section>${action && availability ? `<section aria-label="Safe action"><h2>${text(action)} ${text(screen.title)}</h2><p>${text(availability.reason)}</p><dialog aria-labelledby="confirm-title"><form method="dialog"><h2 id="confirm-title">Confirm ${text(action)}</h2><p>This sends a typed, auditable request to the Product API. It never exposes workflow definitions or credentials.</p><label>Reason <textarea required maxlength="280" name="reason"></textarea></label><label><input type="checkbox" required> I confirm the selected record and scope.</label><button value="cancel">Cancel</button><button value="confirm">Confirm ${text(action)}</button></form></dialog></section>` : ''}</main>`;
}

async function boot() {
  const root = document.querySelector('#app'); if (!root) return;
  const config = await operatorRuntimeConfig(); const session = await operatorSession(config); if (!session) { root.innerHTML = `${renderUnavailable('Sign in through LiNKplatform, then return to this console.')}<button type="button" data-sign-in>Sign in through LiNKplatform</button>`; root.querySelector<HTMLButtonElement>('[data-sign-in]')?.addEventListener('click', () => { void startOperatorSignIn(config).catch((error) => { root.innerHTML = renderUnavailable(error instanceof Error ? error.message : 'Platform sign-in is unavailable.'); }); }); return; }
  const client = new ProductApiClient(transport(session, config.productApiOrigin)); let feedback = '';
  const refresh = async () => {
    const selected = routeFor(location.hash); const resource = resourceFor[selected]; const result = await client.list(resource); root.innerHTML = render(session, selected, result, feedback);
    const action = actionFor(selected, result); const dialog = root.querySelector<HTMLDialogElement>('dialog');
    root.querySelectorAll<HTMLButtonElement>('[data-action]').forEach((button) => button.addEventListener('click', () => { if (dialog) { const selectedAction = button.dataset.action ?? 'action'; dialog.dataset.recordId = button.dataset.recordId ?? ''; dialog.dataset.action = selectedAction; const title = dialog.querySelector('#confirm-title'); if (title) title.textContent = `Confirm ${selectedAction}`; const confirm = dialog.querySelector<HTMLButtonElement>('button[value="confirm"]'); if (confirm) confirm.textContent = `Confirm ${selectedAction}`; dialog.showModal(); } }));
    dialog?.addEventListener('close', async (event) => {
      const closed = event.currentTarget as HTMLDialogElement; const selectedAction = closed.dataset.action as OperatorAction | undefined; if (closed.returnValue !== 'confirm' || !selectedAction) return;
      const form = closed.querySelector('form'); const reason = new FormData(form ?? undefined).get('reason'); const id = closed.dataset.recordId;
      if (!id || typeof reason !== 'string' || !reason.trim()) { feedback = 'Choose a record and provide a reason before retrying.'; await refresh(); return; }
      const record = result.state === 'ready' ? result.value.find((item) => item.id === id) : undefined;
      if (!record || actionForRecord(selected, record) !== selectedAction || !isOperatorActionAllowed(resource, selectedAction)) { feedback = 'That action is not available for this resource or current state.'; await refresh(); return; }
      const outcome = await client.action(resource, id, { action: selectedAction, reason: reason.trim(), idempotencyKey: idempotencyKey(), expectedVersion: record?.version });
      feedback = outcome.state === 'ready' ? `${selectedAction} request recorded for ${outcome.value.id}. Audit receipt: ${outcome.value.auditReference ?? outcome.value.correlationId ?? outcome.value.evidenceRef ?? 'durable record committed'}.` : `${outcome.error.message} Correlation: ${outcome.error.correlationId}.`;
      await refresh();
    });
  };
  addEventListener('hashchange', () => { void refresh(); }); await refresh();
}
addEventListener('DOMContentLoaded', () => { void boot(); });
