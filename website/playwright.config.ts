import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests/browser', workers: 1, use: { baseURL: 'http://127.0.0.1:4327', headless: true }, webServer: { command: 'npm run preview -- --host 127.0.0.1 --port 4327 --strictPort', url: 'http://127.0.0.1:4327', reuseExistingServer: false, timeout: 30000 } });
