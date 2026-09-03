/* 浏览器版的端到端验收。★ 单独跑，不进 `npm test` —— 它要下一个真浏览器，
   不该让每条流水线都等这一下。CI 里是 .github/workflows/e2e.yml。 */
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,              // 第一次要解开十几 MB 的 Pyodide，慢机器上会很久
  expect: { timeout: 20_000 },
  fullyParallel: false,          // 就一份 dist，别互相踩
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8431",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python3 -m http.server 8431 --bind 127.0.0.1 --directory dist",
    url: "http://127.0.0.1:8431/index.html",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
