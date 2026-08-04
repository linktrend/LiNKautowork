import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: [
      'gateway/tests/**/*.test.ts',
      'packages/automation-catalog/test/**/*.test.mjs',
    ],
    coverage: {
      enabled: false,
    },
  },
});
