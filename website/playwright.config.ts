import { defineConfig } from '@playwright/test';
const port = Number(process.env.PLAYWRIGHT_PORT ?? 4327);
export default defineConfig({ testDir: './tests/browser', workers: 1, use: { baseURL: `http://127.0.0.1:${port}`, headless: true }, webServer: { command: `npm run preview -- --host 127.0.0.1 --port ${port} --strictPort`, url: `http://127.0.0.1:${port}`, reuseExistingServer: false, timeout: 30000 } });
