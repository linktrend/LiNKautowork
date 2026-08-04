import { execFile } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

const execute = promisify(execFile);

/** Invokes WP-02's exported validator against one repository-bounded candidate directory. */
export async function validateWp02Package(packagePath: string): Promise<{ errors: Array<{ code: string }> }> {
  const repoRoot = process.cwd(); const packageDir = path.resolve(repoRoot, packagePath);
  if (!packageDir.startsWith(`${path.resolve(repoRoot, 'automations')}${path.sep}`)) return { errors: [{ code: 'unsafe-package-path' }] };
  const moduleUrl = pathToFileURL(path.resolve(repoRoot, 'packages/automation-catalog/src/catalog.mjs')).href;
  const program = `const m=await import(${JSON.stringify(moduleUrl)});const r=m.validatePackageDirectory({repoRoot:process.argv[1],packageDir:process.argv[2]});process.stdout.write(JSON.stringify({errors:r.errors.map(e=>({code:e.code}))}));`;
  const { stdout } = await execute(process.execPath, ['--input-type=module', '--eval', program, repoRoot, packageDir], { maxBuffer: 1024 * 1024 });
  return JSON.parse(stdout) as { errors: Array<{ code: string }> };
}
