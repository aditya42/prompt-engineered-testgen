import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './generated_tests',
  testMatch: '**/*.spec.ts',
  use: { baseURL: 'http://127.0.0.1:4173' },
  reporter: [
    ['list'],
    ['json', { outputFile: 'reports/playwright-results.json' }],
  ],
  webServer: {
    command: 'npm run demo',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
  },
});
