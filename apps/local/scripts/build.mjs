/* 把连环出一份「浏览器版」到 dist/：core/web/index.html 的副本 ＋ 起点脚本 ＋ 后端 zip ＋ 四个纯 Python 轮子 ＋ 自己的 sw.js。
   ★ 源文件一个字节不动；每一处替换都断言命中次数（跟 apps/preview 同一个做法）。
   ★ 需要网络：轮子从 PyPI 下（缓存在 .wheels/）。需要 zip 命令（macOS / Linux 自带）。 */
import { access, cp, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));   // apps/local
const repo = dirname(dirname(here));
const src  = join(repo, "core", "web");
const dist = join(here, "dist");
const there = async (p) => { try { await access(p); return true; } catch { return false; } };
const keep = (p) => { const n = basename(p); return n !== ".DS_Store" && !/\.bak/.test(n); };

/* 钉死的四个纯 Python 轮子（pydantic 1.x：pydantic-core 没有 wasm 轮子；后端全套测试在 1.x 下照过） */
const WHEELS = [["fastapi", "0.115.14"], ["starlette", "0.46.2"], ["pydantic", "1.10.26"], ["python-multipart", "0.0.32"]];

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "wheels"), { recursive: true });
for (const f of ["index.html", "html2canvas.min.js", "manifest.json"]) await cp(join(src, f), join(dist, f));
await cp(join(src, "icons"), join(dist, "icons"), { recursive: true, filter: keep });
await mkdir(join(dist, "blocks", "water"), { recursive: true });
await cp(join(repo, "blocks", "water", "maple-water.js"), join(dist, "blocks", "water", "maple-water.js"));
await cp(join(here, "local-boot.js"), join(dist, "local-boot.js"));

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
if (!html.includes("serviceWorker.register('sw.js')")) throw new Error("SW 注册不见了：浏览器版要靠它做离线和 bridge");
await writeFile(join(dist, "index.html"), html, "utf8");

/* ── sw.js：把静态清单和版本号写进去 ── */
const files = [];
const walk = async (d, rel = "") => {
  for (const e of await readdir(d, { withFileTypes: true })) {
    const r = rel ? rel + "/" + e.name : e.name;
    if (e.isDirectory()) await walk(join(d, e.name), r); else files.push(r);
  }
};
await walk(dist);
const ver = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: repo }).toString().trim() + "-" + Date.now().toString(36);
let sw = await readFile(join(here, "sw.js"), "utf8");
sw = sw.replace("__VER__", ver).replace("__STATIC__", JSON.stringify(files.concat(["sw.js"]).sort()));
await writeFile(join(dist, "sw.js"), sw, "utf8");

await writeFile(join(dist, "README.txt"),
  "连环 · 浏览器版 —— 构建产物\n============================\n" +
  "打开 index.html（要用静态服务器：python3 -m http.server 8426）。同一份 Python 后端在页面里跑（Pyodide），\n" +
  "数据在这台设备的浏览器 IndexedDB 里。第一次打开要从 CDN 拿 Pyodide（十几 MB），之后由 sw.js 缓存。\n" +
  "整个目录一起上传：index.html 引同目录的 local-boot.js、wheels/、backend.zip、icons/、blocks/water/、html2canvas.min.js、sw.js、manifest.json。\n" +
  "许可：AGPL-3.0-only。\n", "utf8");

let bytes = 0; for (const f of files) bytes += (await stat(join(dist, f))).size;
console.log(`拼好了：dist/ ${files.length + 1} 个文件 · ${(bytes / 1024).toFixed(0)} KB（不含 CDN 上的 Pyodide）`);
console.log("  轮子：" + wheelNames.join("、"));
