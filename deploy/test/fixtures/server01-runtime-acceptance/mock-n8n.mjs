import http from 'node:http';
import { assertNoCredentialHeaders, evaluateAcceptanceSuite, loadAcceptancePackage } from './mock-runtime.mjs';

const HOST = '127.0.0.1';
const PORT = Number(process.env.SERVER01_RUNTIME_ACCEPTANCE_MOCK_PORT ?? 18081);

function json(response, status, body) {
  response.writeHead(status, { 'content-type': 'application/json' });
  response.end(JSON.stringify(body));
}

/**
 * Loopback mock of n8n-shaped status for AW-04. It never proxies to n8n.
 * @param {http.IncomingMessage} request
 * @param {http.ServerResponse} response
 */
function handle(request, response) {
  try {
    assertNoCredentialHeaders(request.headers);
  } catch (error) {
    json(response, 400, { error: error instanceof Error ? error.message : 'refused' });
    return;
  }

  const url = new URL(request.url ?? '/', `http://${HOST}`);
  if (request.method === 'GET' && url.pathname === '/health') {
    json(response, 200, {
      status: 'ok',
      mock: true,
      n8n: false,
      live_n8n_activation: 'hold',
      n8n_dispatched: false,
      server01: 'hold',
    });
    return;
  }

  if (request.method === 'GET' && url.pathname === '/workflow') {
    const { workflow } = loadAcceptancePackage();
    json(response, 200, { id: workflow.id, active: workflow.active, imported: false, n8n_dispatched: false });
    return;
  }

  if (request.method === 'POST' && url.pathname === '/eval') {
    const result = evaluateAcceptanceSuite();
    json(response, result.verdict === 'passed' ? 200 : 422, {
      verdict: result.verdict,
      receiptDigest: result.receiptDigest,
      live_n8n_activation: 'hold',
    });
    return;
  }

  json(response, 404, { error: 'mock route not found' });
}

if (process.argv.includes('--self-test')) {
  const result = evaluateAcceptanceSuite();
  process.stdout.write(`${JSON.stringify({ verdict: result.verdict, receiptDigest: result.receiptDigest, cases: result.results.map((item) => item.caseId) })}\n`);
  if (result.verdict !== 'passed') process.exitCode = 1;
} else {
  http.createServer(handle).listen(PORT, HOST, () => {
    process.stdout.write(`${JSON.stringify({ mock: true, listen: `${HOST}:${PORT}`, n8n: false })}\n`);
  });
}
