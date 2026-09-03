/* 把连环出一份「浏览器版」到 dist/：core/web/index.html 的副本 ＋ 起点脚本 ＋ 后端 zip ＋ 纯 Python 轮子 ＋ Pyodide ＋ p5 ＋ 自己的 sw.js。
   ★ **一个第三方 CDN 都不连。** 这个源下面存着模型 key 和整份家（IndexedDB），
     在同一个源上执行别人服务器发来的脚本，等于把那道边界让出去。所以 Pyodide 和 p5 都随包自托管，
     再用 CSP 把 script-src 钉死成 'self'。
   ★ 源文件一个字节不动；每一处替换都断言命中次数（跟 apps/preview 同一个做法）。
   ★ 需要网络：轮子从 PyPI 下（缓存在 .wheels/）。需要 zip 命令（macOS / Linux 自带）。 */
import { access, cp, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));   // apps/local
const repo = dirname(dirname(here));
const src  = join(repo, "core", "web");
const dist = join(here, "dist");
const there = async (p) => { try { await access(p); return true; } catch { return false; } };
const keep = (p) => { const n = basename(p); return n !== ".DS_Store" && !/\.bak/.test(n); };

/* p5.js：版本、文件和摘要一起钉死。源码仓库与浏览器产物共用这一份。 */
const P5 = { file: "p5-1.9.4.min.js", sha256: "00a532c56e785c68d7c7bb6f9a084e2c856b71527f22c3260aff4a2f582d80c9" };

/* 钉死的四个纯 Python 轮子（pydantic 1.x：pydantic-core 没有 wasm 轮子；后端全套测试在 1.x 下照过） */
const WHEELS = [["fastapi", "0.115.14"], ["starlette", "0.46.2"], ["pydantic", "1.10.26"], ["python-multipart", "0.0.32"]];

/* Pyodide 自己那套里要用到的包（页面启动时 loadPackage 的就是这一串）。
   它们不是 PyPI 纯 py 轮子，是 Pyodide 自己编译分发的。 */
const RUNTIME_PACKAGES = ["micropip", "sqlite3", "httpx", "anyio", "sniffio", "typing-extensions", "ssl"];

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "wheels"), { recursive: true });
for (const f of ["index.html", "html2canvas.min.js", "manifest.json"]) await cp(join(src, f), join(dist, f));
await cp(join(src, "icons"), join(dist, "icons"), { recursive: true, filter: keep });
await mkdir(join(dist, "blocks", "water"), { recursive: true });
await cp(join(repo, "blocks", "water", "maple-water.js"), join(dist, "blocks", "water", "maple-water.js"));
await cp(join(here, "local-boot.js"), join(dist, "local-boot.js"));   // 里头的占位稍后按 dist 真实内容填

/* ── 轮子：PyPI 的 JSON 接口找 py3-none-any，下到 .wheels/ 缓存，再拷进 dist ── */
const cache = join(here, ".wheels");
await mkdir(cache, { recursive: true });
const wheelNames = [];
for (const [name, ver] of WHEELS) {
  const meta = await (await fetch(`https://pypi.org/pypi/${name}/${ver}/json`)).json();
  const w = meta.urls.find((u) => u.filename.endsWith("py3-none-any.whl"));
  if (!w) throw new Error(`${name}==${ver} 没有纯 Python 轮子`);
  const local = join(cache, w.filename);
  if (!(await there(local))) {
    const buf = Buffer.from(await (await fetch(w.url)).arrayBuffer());
    await writeFile(local, buf);
  }
  await cp(local, join(dist, "wheels", w.filename));
  wheelNames.push(w.filename);
}

/* ── 后端：core/ optional/ seed/ 打成 zip（不带 index.html 那 1MB、不带备份和缓存） ── */
execFileSync("zip", ["-qr", join(dist, "backend.zip"), "core", "optional", "seed",
  "-x", "*/__pycache__/*", "*.pyc", "*.bak*", "*/node_modules/*", "*.DS_Store",
  "core/web/index.html", "core/web/html2canvas.min.js"], { cwd: repo });

/* ── index.html：跟 preview 一样的补壳与改路径，但保留 sw 注册和 manifest ── */
let html = await readFile(join(dist, "index.html"), "utf8");
function swap(label, needle, replacement, expect) {
  const n = html.split(needle).length - 1;
  if (n !== expect) throw new Error(`「${label}」预期命中 ${expect} 处，实际 ${n} 处 —— core/web/index.html 变了，先看清再改这个脚本`);
  html = html.split(needle).join(replacement);
}
if (!html.startsWith('<meta charset="utf-8">')) throw new Error("源文件不再以 <meta charset> 开头");
if (/<(html|head|body)[\s>]/i.test(html.replace(/<script[\s\S]*?<\/script>/gi, ""))) throw new Error("源文件里已经有 <html>/<head>/<body>");
html = '<!doctype html>\n<html lang="zh-CN">\n<head>\n' +
  '<script id="lh-wheels" type="application/json">' + JSON.stringify(wheelNames) + '</script>\n' +
  '<script src="local-boot.js"></script>\n' + html;                       // ★ 必须排在页面所有脚本前面：它要先把 fetch 换掉
swap("head→body 分界", "\n<!-- ══ 开屏 ══", "\n</head>\n<body>\n\n<!-- ══ 开屏 ══", 1);
if (!/<\/script>\s*$/.test(html)) throw new Error("源文件不再以 </script> 收尾");
html = html.replace(/\s*$/, "\n") + "</body>\n</html>\n";
swap("颜文字样式表", '<link rel="stylesheet" href="/kaomoji/vendor/styles.css">\n', "", 1);
{
  const re = /<script type="importmap">[\s\S]*?<\/script>\s*<script type="module">[\s\S]*?kaomoji-repo\.js[\s\S]*?<\/script>\n?/;
  const hits = (html.match(new RegExp(re.source, "g")) || []).length;
  if (hits !== 1) throw new Error("颜文字抽屉那段：期望命中 1 次，实际 " + hits);
  html = html.replace(re, "<!-- 浏览器版：颜文字抽屉的模块脚本页面一开就要，那时后端还没起来，这一版先不带 -->\n");
}
swap("manifest 链接", 'href="/manifest.json"', 'href="manifest.json"', 1);
swap("图标路径", 'href="/icons/', 'href="icons/', 2);
swap("出图脚本路径", "sc.src = '/html2canvas.min.js';", "sc.src = 'html2canvas.min.js';", 1);
swap("开屏水面脚本路径", "load('/blocks/water/maple-water.js?v='", "load('blocks/water/maple-water.js?v='", 1);

/* ★ CSP：把「这个源上只跑自己的脚本」写死。
   这个源下面存着模型 key 和整份家，第三方脚本一旦能在这儿执行，那道边界就没了。
   · script-src 'self'（＋ inline，因为整页就是一大段内联脚本；＋ wasm-unsafe-eval，Pyodide 要）
   · connect-src 放 https:，因为模型接口地址是用户自己填的，不可能提前列出来；但 http: 和 ws: 关掉
   · frame-ancestors / form-action 关死，object-src 关死 */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' blob:",
  "script-src-attr 'none'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "media-src 'self' data: blob:",
  "connect-src 'self' https: data: blob:",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");
html = html.replace("<head>\n", `<head>\n<meta http-equiv="Content-Security-Policy" content="${CSP}">\n`);
if (!html.includes("Content-Security-Policy")) throw new Error("CSP 没插进去");
if (!html.includes("serviceWorker.register('sw.js')")) throw new Error("SW 注册不见了：浏览器版要靠它做离线和 bridge");
await writeFile(join(dist, "index.html"), html, "utf8");

/* ── Pyodide 自托管 ──
   先在 Node 里把要用的包加载一遍：pyodide 会把缺的轮子下到 node_modules 缓存里，
   然后整个目录挑着拷进 dist/pyodide/。★ 这样页面上 `indexURL` 指的是自己家，不是 jsdelivr。 */
const require_ = createRequire(import.meta.url);
const pyodideDir = dirname(require_.resolve("pyodide"));
{
  const { loadPyodide } = await import("pyodide");
  const py = await loadPyodide({ indexURL: pyodideDir + "/" });
  await py.loadPackage(RUNTIME_PACKAGES);          // 缺的会下下来并缓存进 node_modules
  console.log("  Pyodide 运行时包备齐：" + RUNTIME_PACKAGES.join("、"));
}
await mkdir(join(dist, "pyodide"), { recursive: true });
{
  /* 只拷跑得起来要的：加载器 + 解释器 + 标准库 + 包清单 + 轮子。
     .map / .d.ts / .mjs / console.html / README 一概不带。 */
  let n = 0;
  for (const e of await readdir(pyodideDir, { withFileTypes: true })) {
    if (!e.isFile()) continue;
    const f = e.name;
    const wanted = f === "pyodide.js" || f === "pyodide.asm.js" || f === "pyodide.asm.wasm"
      || f === "python_stdlib.zip" || f === "pyodide-lock.json"
      || f.endsWith(".whl") || (f.endsWith(".zip") && f !== "python_stdlib.zip");
    if (!wanted) continue;
    await cp(join(pyodideDir, f), join(dist, "pyodide", f));
    n++;
  }
  if (n < 6) throw new Error("Pyodide 只拷到 " + n + " 个文件，不对");
  console.log(`  Pyodide 自托管：${n} 个文件`);
}

/* ── p5 自托管：不下载；仓库内固定文件的摘要不对就拒绝出产物 ── */
await mkdir(join(dist, "vendor"), { recursive: true });
{
  const sourceP5 = join(src, "vendor", P5.file);
  const digest = createHash("sha256").update(await readFile(sourceP5)).digest("hex");
  if (digest !== P5.sha256) throw new Error(`p5 SHA-256 不对：${digest}`);
  await cp(sourceP5, join(dist, "vendor", P5.file));
}

/* ── sw.js：把静态清单和版本号写进去 ── */
const files = [];
const walk = async (d, rel = "") => {
  for (const e of await readdir(d, { withFileTypes: true })) {
    const r = rel ? rel + "/" + e.name : e.name;
    if (e.isDirectory()) await walk(join(d, e.name), r); else files.push(r);
  }
};
await walk(dist);
/* 填一个占位。★ 要求它**正好出现一次**，填完再确认一个不剩 ——
   `String.replace(字符串, …)` 只换第一处，而我在注释里也写过同一个词，
   结果换掉的是注释、真正那行原封不动，页面照样死锁。（0903 栽的。） */
function fill(text, token, value, where) {
  const n = text.split(token).length - 1;
  if (n !== 1) throw new Error(`${where} 里的 ${token} 出现了 ${n} 次，应该正好 1 次`);
  const out = text.split(token).join(value);
  if (out.includes(token)) throw new Error(`${where} 里还剩 ${token} 没填`);
  return out;
}

/* ★ 起点脚本那张「哪些是本站自己的文件」名单，按 dist 的真实内容填 ——
   手写它栽过一次：自托管 Pyodide 后忘了加 pyodide/，wasm 被当成后端请求，页面直接死锁。 */
{
  const prefixes = [...new Set(files.map((f) => (f.includes("/") ? f.split("/")[0] + "/" : f)))].sort();
  const bootPath = join(dist, "local-boot.js");
  const boot = fill(await readFile(bootPath, "utf8"), "__STATIC__", JSON.stringify(prefixes), "local-boot.js");
  await writeFile(bootPath, boot, "utf8");
  console.log("  本站文件前缀：" + prefixes.join("、"));
}

const ver = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: repo }).toString().trim() + "-" + Date.now().toString(36);
let sw = await readFile(join(here, "sw.js"), "utf8");
sw = fill(sw, "__VER__", ver, "sw.js");
sw = fill(sw, "__STATIC__", JSON.stringify(files.concat(["sw.js"]).sort()), "sw.js");
await writeFile(join(dist, "sw.js"), sw, "utf8");

await writeFile(join(dist, "README.txt"),
  "连环 · 浏览器版 —— 构建产物\n============================\n" +
  "打开 index.html（要用静态服务器：python3 -m http.server 8426）。同一份 Python 后端在页面里跑（Pyodide），\n" +
  "数据在这台设备的浏览器 IndexedDB 里。\n" +
  "★ 一个第三方 CDN 都不连：Pyodide 和 p5 都在这个目录里，页面上还钉了 CSP（script-src 只认 'self'）。\n" +
  "  第一次打开要从本站拿十几 MB 的 Pyodide，之后由 sw.js 缓存，离线也能开。\n" +
  "整个目录一起上传：index.html 引同目录的 local-boot.js、pyodide/、vendor/、wheels/、backend.zip、icons/、blocks/water/、html2canvas.min.js、sw.js、manifest.json。\n" +
  "许可：AGPL-3.0-only。\n", "utf8");

let bytes = 0; for (const f of files) bytes += (await stat(join(dist, f))).size;
console.log(`拼好了：dist/ ${files.length + 1} 个文件 · ${(bytes / 1024).toFixed(0)} KB（Pyodide 和 p5 都在里头，跑起来不连任何 CDN）`);
console.log("  轮子：" + wheelNames.join("、"));
