import http from 'node:http';

http.createServer((request, response) => {
  const failure = new URL(request.url, 'http://fake-upstream').pathname === '/fail';
  response.writeHead(failure ? 503 : 200, { 'content-type': 'application/json' });
  response.end(JSON.stringify(failure ? { error: 'deterministic_upstream_failure' } : { ok: true }));
}).listen(8081, '0.0.0.0');
