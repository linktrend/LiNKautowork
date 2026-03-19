export function logInfo(message: string, data?: Record<string, unknown>): void {
  const payload = data ? ` ${JSON.stringify(data)}` : '';
  process.stdout.write(`[INFO] ${message}${payload}\n`);
}

export function logWarn(message: string, data?: Record<string, unknown>): void {
  const payload = data ? ` ${JSON.stringify(data)}` : '';
  process.stdout.write(`[WARN] ${message}${payload}\n`);
}

export function logError(message: string, data?: Record<string, unknown>): void {
  const payload = data ? ` ${JSON.stringify(data)}` : '';
  process.stderr.write(`[ERROR] ${message}${payload}\n`);
}
