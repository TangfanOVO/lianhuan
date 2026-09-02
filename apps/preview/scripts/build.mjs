/* 把 core/web/index.html 出一份「诚实空壳」预览到 dist/ —— 零依赖，只用 node 自带的 fs/path。
   ════════════════════════════════════════════════════════════════
   产物是 core/web/ 的**副本**＋一段横条（banner.js），没有后端。
   ★ 源文件一个字节不动：所有替换都落在 dist/index.html 上。
   ★ 每一处替换都断言命中次数 —— 源文件哪天变了，这里会直接报错退出，不会静默出一份坏副本。
   ★ 不拷 sw.js / manifest.json：装一个指着错地方的 Service Worker 比不装糟得多——
     发到站根的话它会把别人的首页当离线壳缓存下来。 */
import { access, cp, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));   // apps/preview
const repo = dirname(dirname(here));                             // 仓库根
const src  = join(repo, "core", "web");
const dist = join(here, "dist");
const there = async (p) => { try { await access(p); return true; } catch { return false; } };

/* 拷目录时挡掉的：系统垃圾、备份 */
function keep(p) {
  const n = basename(p);
  return n !== ".DS_Store" && !/\.bak/.test(n);
}

/* ── 1. 白名单拷贝 ── */
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
for (const f of ["index.html", "html2canvas.min.js"]) await cp(join(src, f), join(dist, f));
await cp(join(src, "icons"), join(dist, "icons"), { recursive: true, filter: keep });
await cp(join(here, "banner.js"), join(dist, "banner.js"));
/* 开屏那层水是从积木层拉的（blocks/water/，MIT），index.html 里是站根绝对路径。
   只拿这一个文件，它自包含（不再 import/fetch 别的）；README/demo 不带。 */
await mkdir(join(dist, "blocks", "water"), { recursive: true });
await cp(join(repo, "blocks", "water", "maple-water.js"), join(dist, "blocks", "water", "maple-water.js"));

/* ── 2. 纯文本替换（改的是副本） ── */
let html = await readFile(join(dist, "index.html"), "utf8");

/* 命中次数对不上就抛 —— 别静默跳过 */
function swap(label, needle, replacement, expect) {
  const n = html.split(needle).length - 1;
  if (n !== expect) {
    throw new Error(`「${label}」预期命中 ${expect} 处，实际 ${n} 处 —— core/web/index.html 变了，先看清再改这个脚本`);
  }
  html = html.split(needle).join(replacement);
}

/* a. 补 doctype / html / head / body。源文件第 1 行就是 <meta charset>，没有这四样，
      浏览器跑在怪异模式。head 区到最后一个 </style> 为止，接着是开屏那段注释＋ <div id="splash">。 */
if (!html.startsWith('<meta charset="utf-8">')) throw new Error("源文件不再以 <meta charset> 开头，head 的位置要重新看");
if (/<(html|head|body)[\s>]/i.test(html.replace(/<script[\s\S]*?<\/script>/gi, ""))) {
  throw new Error("源文件里已经有 <html>/<head>/<body> 了，不该再补");
}
html = '<!doctype html>\n<html lang="zh-CN">\n<head>\n' + html;
swap("head→body 分界", "\n<!-- ══ 开屏 ══", "\n</head>\n<body>\n\n<!-- ══ 开屏 ══", 1);
if (!/<\/script>\s*$/.test(html)) throw new Error("源文件不再以 </script> 收尾，末尾追加的位置要重新看");
html = html.replace(/\s*$/, "\n") + '<script src="banner.js"></script>\n</body>\n</html>\n';   // d. 横条脚本

/* b. 颜文字抽屉的样式表在 optional/ 里，静态托管必 404 —— 整行删掉 */
swap("颜文字样式表", '<link rel="stylesheet" href="/kaomoji/vendor/styles.css">\n', "", 1);
/* ★ 0902 验收逮到的：光删样式表不够。文件末尾那段颜文字抽屉是 importmap + <script type="module">，
   模块脚本的**静态 import 页面一开就发**，/kaomoji/vendor/react.js 等 4 个在静态托管下必 404。
   整段摘掉（从 importmap 开始、到那个 module 脚本的 </script> 为止）。 */
{
  const re = /<script type="importmap">[\s\S]*?<\/script>\s*<script type="module">[\s\S]*?kaomoji-repo\.js[\s\S]*?<\/script>\n?/;
  const hits = (html.match(new RegExp(re.source, "g")) || []).length;
  if (hits !== 1) throw new Error("颜文字抽屉那段：期望命中 1 次，实际 " + hits);
  html = html.replace(re, "<!-- 静态预览：颜文字抽屉的资源在 optional/ 里，静态托管拿不到，整段摘掉了 -->\n");
  console.log("  摘掉颜文字抽屉 importmap + module 脚本 ✓");
}
/* favicon：源文件本来就带 <link rel="icon" href="/icons/icon.svg">，上面「图标路径」那条 swap 已经把它改成相对的了，
   **别再加一条**（0902 加过一次，副本里出现了两个 icon 链接）。 */

/* c. Service Worker 注册：副本不带 sw.js，注册必失败，不如不注册。两处写法不同，分开换。
      ⚠ 不能把两处都机械换成 void 0 ——
        进门那处是 `register('sw.js').catch(...)`，换出来是 `void 0.catch(...)`，那是 SyntaxError，整段脚本都跑不了；
        推送那处后面紧跟 `await navigator.serviceWorker.ready`，没有注册它永远不 resolve，开关会停在「开通中」。
        所以进门那处连 .catch 一起换成 void 0；推送那处换成一个会被它自己 catch 住的 reject，界面照实说开不了。 */
swap("SW 注册（进门）", "navigator.serviceWorker.register('sw.js').catch(function(){})", "void 0", 1);
swap("SW 注册（推送）", "await navigator.serviceWorker.register('sw.js')",
     "await Promise.reject(new Error('静态预览没有 sw.js，推送开不了'))", 1);
if (html.includes("serviceWorker.register(")) throw new Error("还剩没换掉的 SW 注册");

/* e. 副本挂在子路径（/app/）下，站根的绝对路径够不着自己带的文件 —— 改成相对的。
      manifest 没有随副本一起发，链接也一并摘掉，免得每次开页一个 404。 */
swap("manifest 链接", '<link rel="manifest" href="/manifest.json">\n', "", 1);
swap("图标路径", 'href="/icons/', 'href="icons/', 2);
swap("出图脚本路径", "sc.src = '/html2canvas.min.js';", "sc.src = 'html2canvas.min.js';", 1);
swap("开屏水面脚本路径", "load('/blocks/water/maple-water.js?v='", "load('blocks/water/maple-water.js?v='", 1);

/* ── 3. 简单解析一遍，确认标签配平 ── */
function checkShape(doc) {
  const marks = ['<!doctype html>', '<html lang="zh-CN">', "<head>", "</head>", "<body>", "</body>", "</html>"];
  const at = marks.map((m) => {
    const n = doc.split(m).length - 1;
    if (n !== 1) throw new Error(`${m} 出现了 ${n} 次，应该正好 1 次`);
    return doc.indexOf(m);
  });
  if (at[0] !== 0) throw new Error("第一行不是 doctype");
  for (let i = 1; i < at.length; i++) if (at[i] <= at[i - 1]) throw new Error(`${marks[i]} 排在 ${marks[i - 1]} 前面了`);
  /* 先剥 script/style 再剥注释：脚本里的字符串要是含 <!--，反过来会把后面的 </script> 一起吞掉 */
  const strip = (s) => s.replace(/<script[\s\S]*?<\/script>/gi, "")
                        .replace(/<style[\s\S]*?<\/style>/gi, "")
                        .replace(/<!--[\s\S]*?-->/g, "");
  /* head 区只许 meta / link / title（style、script、注释已剥掉） */
  const head = strip(doc.slice(at[2] + "<head>".length, at[3]));
  const bad = [...head.matchAll(/<([a-zA-Z][\w-]*)/g)].map((m) => m[1].toLowerCase())
    .filter((t) => !["meta", "link", "title"].includes(t));
  if (bad.length) throw new Error("head 区里混进了 " + [...new Set(bad)].join(","));
  /* body 区不许再冒出 html / head / body 开标签 */
  const body = strip(doc.slice(at[4] + "<body>".length, at[5]));
  if (/<(html|head|body)[\s>]/i.test(body)) throw new Error("body 区里又出现了 html/head/body 标签");
  if (!/<\/html>\s*$/.test(doc)) throw new Error("文件不是以 </html> 收尾");
}
checkShape(html);
await writeFile(join(dist, "index.html"), html, "utf8");

/* ── 4. 数一遍产物，确认没把不该带的带上 ── */
for (const f of ["sw.js", "manifest.json"]) {
  if (await there(join(dist, f))) throw new Error(`dist 里不该有 ${f}`);
}
let files = 0, bytes = 0;
const walk = async (d) => {
  for (const e of await readdir(d, { withFileTypes: true })) {
    const p = join(d, e.name);
    if (e.isDirectory()) await walk(p);
    else { files++; bytes += (await stat(p)).size; }
  }
};
await walk(dist);

await writeFile(join(dist, "README.txt"),
  "连环 · 应用空壳预览 —— 构建产物\n" +
  "==================================\n" +
  "这是 core/web/index.html 的副本，加了一条页顶横条。**没有后端。**\n" +
  "  · 所有 /api/* 都是 404，页面按它自己的降级逻辑显示空状态——那些空是真的空，不是演示数据。\n" +
  "  · 发消息、打电话两个入口被拦下并说明原因；输入框里的字不会被清掉，也不会伪造回复。\n" +
  "  · 颜文字抽屉、桌宠素材、推送、离线壳都不在这份里（前两样在 optional/，后两样故意没带 sw.js / manifest.json）。\n" +
  "  · 设置里的外观项存在本机 localStorage，只在这台机器、这个浏览器里有效。\n\n" +
  "本地看一眼：在这个目录里跑 `python3 -m http.server 8425`，然后开 http://localhost:8425\n" +
  "（直接双击 index.html 也能开个大概，但 file:// 下各种路径都不对，起个静态服务器最省事。）\n\n" +
  "★ 发布时整个目录一起上传：index.html 引的是同目录下的 icons/、blocks/water/、html2canvas.min.js、banner.js。\n" +
  "许可：AGPL-3.0-only（与完整的连环应用相同）。\n", "utf8");

console.log(`拼好了：dist/ ${files} 个文件 · ${(bytes / 1024).toFixed(0)} KB`);
console.log("  副本不带 sw.js / manifest.json；SW 注册已摘；横条脚本 banner.js 已追加。");
