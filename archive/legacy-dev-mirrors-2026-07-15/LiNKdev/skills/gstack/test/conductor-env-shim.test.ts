import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { promoteConductorEnv } from '../lib/conductor-env-shim';

describe('conductor-env-shim', () => {
  const KEYS = ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GSTACK_ANTHROPIC_API_KEY', 'GSTACK_OPENAI_API_KEY'] as const;
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const k of KEYS) {
      saved[k] = process.env[k];
      delete process.env[k];
    }
  });

  afterEach(() => {
    for (const k of KEYS) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  });

  test('promotes GSTACK_ANTHROPIC_API_KEY to ANTHROPIC_API_KEY when canonical is empty', () => {
    process.env.GSTACK_ANTHROPIC_API_KEY = 'ltfx.ant.test123.v1';
    promoteConductorEnv();
    expect(process.env.ANTHROPIC_API_KEY).toBe('ltfx.ant.test123.v1');
  });

  test('promotes GSTACK_OPENAI_API_KEY to OPENAI_API_KEY when canonical is empty', () => {
    process.env.GSTACK_OPENAI_API_KEY = 'ltfx.oai.test456.v1';
    promoteConductorEnv();
    expect(process.env.OPENAI_API_KEY).toBe('ltfx.oai.test456.v1');
  });

  test('does not overwrite canonical when both canonical and GSTACK_-prefixed are set', () => {
    process.env.ANTHROPIC_API_KEY = 'ltfx.ant.original.v1';
    process.env.GSTACK_ANTHROPIC_API_KEY = 'ltfx.ant.prefixed.v1';
    promoteConductorEnv();
    expect(process.env.ANTHROPIC_API_KEY).toBe('ltfx.ant.original.v1');
  });

  test('no-op when neither canonical nor GSTACK_-prefixed are set', () => {
    promoteConductorEnv();
    expect(process.env.ANTHROPIC_API_KEY).toBeUndefined();
    expect(process.env.OPENAI_API_KEY).toBeUndefined();
  });
});
