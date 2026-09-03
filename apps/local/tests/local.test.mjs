import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, readdir, access } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(here, "dist");
const there = async (p) => { try { await access(p); return true; } catch { return false; } };

test("★ 先构建过（npm run build）", async () => { assert.ok(await there(join(dist, "index.html")), "没有 dist/，先 npm run build"); });

test("起点脚本排在页面所有脚本前面，颜文字抽屉那段摘掉了", async () => {
  const html = await readFile(join(dist, "index.html"), "utf8");
  const boot = html.indexOf('<script src="local-boot.js">');
  const firstOther = html.replace('<script src="local-boot.js"></script>', "").replace(/<script id="lh-wheels"[\s\S]*?<\/script>/, "").indexOf("<script");
  assert.ok(boot > 0 && boot < html.indexOf("</head>"), "local-boot.js 要在 head 里");
  assert.ok(html.indexOf("<script src=\"local-boot.js\">") < html.indexOf("<script", boot + 10), "别的脚本不能排在它前面");
  assert.ok(firstOther > 0);
  assert.ok(!html.includes("/kaomoji/"), "颜文字抽屉的资源页面一开就要，这一版不带");
  assert.ok(html.includes("serviceWorker.register('sw.js')"), "浏览器版要注册 sw.js");
  assert.ok(!html.includes('href="/icons/') && !html.includes('href="/manifest.json"'), "站根绝对路径在子路径下够不着");
});

test("后端 zip 带了该带的、没带不该带的", () => {
  const list = execFileSync("unzip", ["-Z1", join(dist, "backend.zip")]).toString().split("\n");
  for (const must of ["core/server.py", "core/browser.py", "core/store/sqlite.py", "optional/reading/routes.py", "seed/demo.json"])
    assert.ok(list.includes(must), must + " 不在 backend.zip 里");
  assert.ok(!list.includes("core/web/index.html"), "那 1MB 的页面不该进后端 zip");
  assert.ok(!list.some((f) => /\.bak|__pycache__|node_modules/.test(f)), "备份/缓存混进去了");
});

test("四个纯 Python 轮子都在，sw.js 的清单里有它们", async () => {
  const wheels = (await readdir(join(dist, "wheels"))).filter((f) => f.endsWith(".whl"));
  assert.equal(wheels.length, 4, wheels.join(","));
  const sw = await readFile(join(dist, "sw.js"), "utf8");
  for (const w of wheels) assert.ok(sw.includes("wheels/" + w), w + " 不在 sw 清单里");
  for (const must of ["backend.zip", "local-boot.js", "manifest.json"]) assert.ok(sw.includes('"' + must + '"'), must);
  assert.ok(!sw.includes("__VER__") && !sw.includes("__STATIC__"), "占位没替换");
});

test("★ 一个第三方 CDN 都不连（这个源下面存着 key 和整份家）", async () => {
  const html = await readFile(join(dist, "index.html"), "utf8");
  const boot = await readFile(join(dist, "local-boot.js"), "utf8");
  const sw = await readFile(join(dist, "sw.js"), "utf8");
  const urls = [...(html + boot + sw).matchAll(/https?:\/\/[^\s"'`)]+/g)].map((m) => m[0])
    .filter((u) => !u.startsWith("http://127.0.0.1") && !u.startsWith("http://localhost"));
  const bad = urls.filter((u) =>
    !/api\.deepseek\.com/.test(u)            // 设置页里的示例接口地址，不是脚本
    && !/^https?:\/\/www\.w3\.org\//.test(u));  // SVG/XML 的命名空间，浏览器不会去取
  assert.deepEqual(bad, [], "还在连外面：" + bad.join("、"));
  for (const host of ["cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com"]) {
    assert.ok(!(html + boot + sw).includes(host), "还引着 " + host);
  }
});

test("★ CSP 把 script-src 钉死成自己", async () => {
  const html = await readFile(join(dist, "index.html"), "utf8");
  const m = /content="(default-src[^"]*)"/.exec(html);
  assert.ok(m, "没有 CSP");
  const csp = m[1];
  assert.match(csp, /script-src 'self'/, "script-src 要以 'self' 打头");
  assert.ok(!/script-src[^;]*https:/.test(csp), "script-src 里不许放开 https:");
  assert.match(csp, /wasm-unsafe-eval/, "Pyodide 要这个");
  assert.match(csp, /object-src 'none'/);
  assert.match(csp, /frame-ancestors 'none'/);
});

test("Pyodide 和 p5 真的随包带了", async () => {
  const py = await readdir(join(dist, "pyodide"));
  for (const must of ["pyodide.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]) {
    assert.ok(py.includes(must), "pyodide/ 少了 " + must);
  }
  assert.ok(py.some((f) => f.startsWith("sqlite3-")), "少了 sqlite3");
  assert.ok(await there(join(dist, "vendor", "p5.min.js")), "少了自带的 p5");
});

test("★ 本站文件清单是构建时生成的，不是手写的", async () => {
  const boot = await readFile(join(dist, "local-boot.js"), "utf8");
  assert.ok(!boot.includes("__STATIC__"), "占位没填 —— 填了才知道哪些请求归后端");
  const m = /var STATIC_PREFIXES = (\[[^\]]*\])/.exec(boot);
  assert.ok(m, "找不到清单");
  const list = JSON.parse(m[1]);
  // ★ 漏一个目录，那个目录里的请求就会被排进「等后端」的队里；
  //   而后端自己正等着 pyodide/ 里的 wasm —— 直接死锁。
  for (const must of ["pyodide/", "vendor/", "wheels/", "icons/", "blocks/", "backend.zip"]) {
    assert.ok(list.includes(must), "清单里少了 " + must);
  }
});

test("★ 起点脚本不指向本机、不带任何 key", async () => {
  const js = await readFile(join(dist, "local-boot.js"), "utf8");
  for (const bad of ["localhost", "127.0.0.1", "/Users/", "sk-"]) assert.ok(!js.includes(bad), "local-boot.js 里出现了 " + bad);
});
