/* 把预览站拼成 dist/ —— 零依赖，就 node 自带的 fs。
   ════════════════════════════════════════════════════════════════
   产物是 **index.html ＋ assets/**（不是单文件）。
   ★ 所以发布的时候**整个 dist 一起上传**，只发一个 index.html 是打不开的。

   assets/blocks/ 里放的是 blocks/ 的**真副本** —— 预览站用 iframe 跑每块自己的 demo，
   所以拷进来的必须是原件，不能是改写过的版本，不然「你看到的不是你拿走的」。 */
import { access, cp, mkdir, readdir, rm, writeFile, stat } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));   // apps/showcase
const repo = dirname(dirname(here));                             // 仓库根
const dist = join(here, "dist");
const there = async (p) => { try { await access(p); return true; } catch { return false; } };

/* 拷 blocks 时挡掉的：构建产物、包管理的东西、备份 */
function keep(src) {
  const n = basename(src);
  if (["dist", "node_modules", "scripts", "tests", "package.json", "package-lock.json"].includes(n)) return false;
  if (n === ".DS_Store" || /\.bak/.test(n)) return false;
  return true;
}

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "assets"), { recursive: true });

for (const f of ["index.html", "showcase.css", "showcase.js", "LICENSE"]) {
  if (await there(join(here, f))) await cp(join(here, f), join(dist, f));
}
await cp(join(repo, "blocks"), join(dist, "assets", "blocks"), { recursive: true, filter: keep });
/* favicon：不带的话浏览器每次都去站根要 /favicon.ico，Pages 上是 404。拿应用那片枫叶（FA，已署名）。 */
if (await there(join(repo, "core", "web", "icons", "icon.svg")))
  await cp(join(repo, "core", "web", "icons", "icon.svg"), join(dist, "icon.svg"));

/* 数一数产物，顺带把「必须整个 dist 一起发」写进产物自己里 */
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
  "连环 · 积木预览 —— 构建产物\n" +
  "================================\n" +
  "这一份是 index.html ＋ assets/。\n" +
  "★ 发布时**整个目录一起上传**：index.html 引的是同目录下的 assets/，\n" +
  "  只单发一个 index.html 打不开。\n\n" +
  "本地看一眼：在这个目录里跑 `python3 -m http.server 8421`，然后开 http://localhost:8421\n" +
  "（直接双击 index.html 也能开大半，但 iframe 里的 demo 走 file:// 会被浏览器挡，\n" +
  "  所以还是起个静态服务器最省事。）\n\n" +
  "许可：预览站与 blocks/ 里的积木是 MIT（见 LICENSE）；完整的连环应用是 AGPL-3.0-only。\n", "utf8");

/* 公开仓库地址还没填的话，吼一声 —— 别让「看源码」那个入口一直空着上线 */
const js = await (await import("node:fs/promises")).readFile(join(dist, "showcase.js"), "utf8");
const repoSet = /var REPO = "(.+?)"/.exec(js)?.[1];
console.log(`拼好了：dist/ ${files} 个文件 · ${(bytes / 1024).toFixed(0)} KB`);
console.log(repoSet
  ? `  「看源码」指向 ${repoSet}`
  : "  ⚠ 公开仓库地址还没填 —— 「看源码」那个入口会照实说还没定（不给假链接）。\n" +
    "    定了改 apps/showcase/showcase.js 顶上的 REPO，只有那一处。");
