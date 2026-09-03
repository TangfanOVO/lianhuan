/* 浏览器版：真浏览器里从头走一遍。
   ★ 这条补的是「合同测试测不到」的那半：Pyodide 在真浏览器里起不起得来、
     写进去的话刷新后还在不在、有没有偷偷连外面。 */
import { test, expect } from "@playwright/test";

/* ★ 不许用 page.waitForFunction：它在页面里 eval 一段字符串，
   而这一版的 CSP 没给 'unsafe-eval' —— 第一次跑就当场被拦（那说明 CSP 是真在管事）。
   page.evaluate 走调试协议的 callFunctionOn，不受 CSP 管，所以自己轮询。
   也**不开** Playwright 的 bypassCSP：开了就验不到 CSP 有没有把自己人拦掉。 */
async function until(page, fn, ms, label) {
  const t0 = Date.now();
  for (;;) {
    if (await page.evaluate(fn)) return;
    if (Date.now() - t0 > ms) throw new Error("等「" + label + "」超时（" + ms + "ms）");
    await page.waitForTimeout(500);
  }
}

/** 打开页面，等里头的后端起来（第一次要解开十几 MB 的 Pyodide，慢）。 */
async function boot(page) {
  const external = [];
  page.on("request", (r) => {
    const u = r.url();
    if (!u.startsWith("http://127.0.0.1:8431") && !u.startsWith("data:") && !u.startsWith("blob:")) {
      external.push(u);
    }
  });
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) =>
      window.__csp.push(e.violatedDirective + " ← " + e.blockedURI));
  });
  await page.goto("/index.html");
  await until(page, () => !!window.__lianhuanLocal, 150000, "后端起来");
  const cspHits = await page.evaluate(() => window.__csp || []);
  return { external, cspHits };
}

test("起得来，而且一个外部请求都没有", async ({ page }) => {
  const { external, cspHits } = await boot(page);
  const info = await page.evaluate(() => window.__lianhuanLocal.info);
  expect(info.ok).toBe(true);
  expect(info.python).toMatch(/^3\./);
  // ★ 这个源下面存着 key 和整份家；同源跑第三方脚本，那道边界就没了
  expect(external, "连了外面：" + external.join("、")).toEqual([]);
  expect(cspHits, "CSP 拦到了自己人：" + cspHits.join("、")).toEqual([]);
});

test("接口通，说一句话能存下来，刷新之后还在", async ({ page }) => {
  await boot(page);

  const status = await page.evaluate(async () => (await fetch("api/distill")).status);
  expect(status).toBe(200);

  const chat = await page.evaluate(async () => {
    const r = await fetch("chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: "端到端验收说的一句话", session_id: "web" }),
    });
    let chunks = 0;
    const rd = r.body.getReader();
    for (;;) { const { done } = await rd.read(); if (done) break; chunks++; }
    return { status: r.status, chunks };
  });
  expect(chat.status).toBe(200);
  expect(chat.chunks, "回复不是流式的").toBeGreaterThan(0);

  // ★ 关键的一条：写完就刷新，最后一次 IndexedDB 同步不能丢
  await page.evaluate(() => window.__lianhuanLocal.flush());
  await page.waitForTimeout(1200);
  await page.reload();
  await until(page, () => !!window.__lianhuanLocal, 150000, "刷新后重新起来");

  const items = await page.evaluate(async () => (await (await fetch("api/hist")).json()).items || []);
  expect(items.length, "刷新之后聊天记录没了").toBeGreaterThanOrEqual(2);
  expect(items.some((t) => (t.content || "").includes("端到端验收说的一句话")), "刚说的那句不见了").toBe(true);
});

test("键盘顶上来时，界面跟着让位", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await boot(page);
  /* 真软键盘没法在无头浏览器里叫出来；这里验的是**接线**：
     --kb 一变，.app 的高度和贴着底边的输入条要跟着走。真机上那个数由 visualViewport 给。 */
  const moved = await page.evaluate(async () => {
    const app = document.querySelector(".app");
    const h0 = app.getBoundingClientRect().height;
    document.documentElement.style.setProperty("--kb", "300px");
    await new Promise((r) => setTimeout(r, 150));
    const h1 = app.getBoundingClientRect().height;
    document.documentElement.style.removeProperty("--kb");
    return h0 - h1;
  });
  expect(moved).toBe(300);
});
