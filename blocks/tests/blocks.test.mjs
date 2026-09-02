/* 积木包的自检。零依赖，node --test 就跑。
   ★ 这几条钉的是**许可边界和「拿走就能用」**，不是渲染效果 ——
     渲染那部分靠每块自己的 demo.html，双击就能看。 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, access, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const pkg = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
const exists = async (p) => { try { await access(join(root, p)); return true; } catch { return false; } };

test("这个包是 MIT，而且 LICENSE 真在里头", async () => {
  assert.equal(pkg.license, "MIT");
  assert.ok(await exists("LICENSE"), "LICENSE 文件不能少 —— MIT 那句话说的就是它要跟着走");
  assert.ok(pkg.files.includes("LICENSE"), "发包的白名单里要含 LICENSE");
});

test("★ 一个依赖都不许有", () => {
  // 这是许可边界的一半：MIT 包一旦依赖了 AGPL 那半边，边界当场破。
  // 人会忘，这条不会。
  for (const field of ["dependencies", "peerDependencies", "optionalDependencies"]) {
    assert.equal(pkg[field], undefined, `${field} 应该根本不存在 —— 这些块是零依赖的`);
  }
});

test("★ 不许从应用那半边 import 任何东西", async () => {
  // 依赖方向只能是「应用 → 积木」。反过来一条都不许有。
  const files = pkg.exports;
  for (const rel of Object.values(files)) {
    if (!rel.endsWith(".js")) continue;
    const src = await readFile(join(root, rel), "utf8");
    for (const bad of ["../core", "../optional", "/api/", "core/web"]) {
      if (rel.includes("robot") && bad === "/api/") continue;   // 机器人那块明说要接你自己的地址
      assert.ok(!src.includes(bad), `${rel} 里出现了 ${bad} —— 积木不该知道后端长什么样`);
    }
  }
});

test("每个 export 指的文件都真在", async () => {
  for (const [name, rel] of Object.entries(pkg.exports)) {
    assert.ok(await exists(rel), `${name} 指向了不存在的 ${rel}`);
  }
});

test("在场的每块都有能单独双击打开的 demo", async () => {
  // ★ 不写死块名：取件器会只带走其中几块，写死的话取一块就红一片。
  //   改成「这个副本里有哪几块，就查哪几块」。
  const { readdir } = await import("node:fs/promises");
  const skip = new Set(["base", "parts", "dist", "scripts", "tests", "node_modules"]);
  for (const e of await readdir(root, { withFileTypes: true })) {
    if (!e.isDirectory() || skip.has(e.name)) continue;
    assert.ok(await exists(`${e.name}/demo.html`) || await exists(`${e.name}/demo-paper.html`),
              `${e.name} 少了 demo —— 拿走之后没法一眼看出它长什么样`);
  }
});

test("★ 不带任何公司的 logo 或吉祥物", async () => {
  // 商标不是许可证能解决的事。0830 从字云默认形状里换掉过一次，别再回来。
  for (const rel of Object.values(pkg.exports)) {
    const src = await readFile(join(root, rel), "utf8");
    for (const bad of ["Clawd", "D_CLAUDE", "D_CCODE"]) {
      assert.ok(!src.includes(bad), `${rel} 里出现了 ${bad}`);
    }
  }
});

test("★ demo 里的外部 <script src> 必须在自己 README 里交代过", async () => {
  // ★ 0902 漏过一次：下面那条「零网络」只 grep 了 js 里的 fetch/WebSocket，
  //   抓不到 demo.html 里一行 `<script src="https://cdn…">`。
  //   water 那块真的要 p5（LGPL，它 README 明写「只走 CDN 不打包」）——
  //   规矩不是「不许有」，是**不许没交代**。
  const { readdir } = await import("node:fs/promises");
  const skip = new Set(["dist", "scripts", "tests", "node_modules"]);
  for (const e of await readdir(root, { withFileTypes: true })) {
    if (!e.isDirectory() || skip.has(e.name)) continue;
    for (const f of await readdir(join(root, e.name))) {
      if (!f.endsWith(".html")) continue;
      const html = await readFile(join(root, e.name, f), "utf8");
      const ext = [...html.matchAll(/<script[^>]+src="(https?:\/\/[^"]+)"/g)].map((m) => m[1]);
      if (!ext.length) continue;
      const readme = await readFile(join(root, e.name, "README.md"), "utf8").catch(() => "");
      for (const url of ext) {
        const lib = url.split("/").find((seg) => /^[a-z0-9.-]+$/i.test(seg) && seg.length > 1) || url;
        assert.ok(/CDN|cdn/.test(readme) && readme.includes(lib.split(".")[0]),
                  `${e.name}/${f} 从外部拉了 ${url}，但 ${e.name}/README.md 没交代这件事`);
      }
    }
  }
});

test("零网络（机器人那块除外，它明说要接你自己的地址）", async () => {
  for (const [name, rel] of Object.entries(pkg.exports)) {
    if (!rel.endsWith(".js") || rel.includes("robot")) continue;
    const src = await readFile(join(root, rel), "utf8");
    for (const bad of ["fetch(", "XMLHttpRequest", "new WebSocket", "EventSource"]) {
      assert.ok(!src.includes(bad), `${name} 发网络请求了（${bad}）—— 积木应该只吃喂进来的数据`);
    }
  }
});

/* ★ 0902 补的。起因：ambience.css 被截断在 `@keyframes fall{ 0%{…}` 那一行——
   没有 100% 帧、没有收尾大括号。CSS 解析器在 EOF 自动闭合，语法「合法」，
   于是漂浮物每一颗都从 -10vh 挪回自己的静态位，全程在容器外，
   overflow:hidden 一裁，一颗都看不见。**没有任何测试逮住它。**
   （更糟的是那个文件头上写着「tests 里钉了一条防漂移」——那条测试压根不存在。） */
test("★ 每个 css 文件都是完整的（大括号配平、keyframes 有头有尾）", async () => {
  const files = [];

  const walk = async (dir) => {
    for (const e of await readdir(dir, { withFileTypes: true })) {
      if (e.name === "dist" || e.name === "node_modules" || e.name.startsWith(".")) continue;
      const p = join(dir, e.name);
      if (e.isDirectory()) await walk(p);
      else if (e.name.endsWith(".css")) files.push(p);
    }
  };
  await walk(root);
  assert.ok(files.length > 0, "一个 css 都没找到，这条测试自己坏了");

  for (const f of files) {
    const css = (await readFile(f, "utf8")).replace(/\/\*[\s\S]*?\*\//g, "");
    let depth = 0;
    for (const ch of css) {
      if (ch === "{") depth++;
      else if (ch === "}") depth--;
      assert.ok(depth >= 0, `${f}：大括号多了一个 }`);
    }
    assert.equal(depth, 0, `${f}：大括号没配平（少 ${depth} 个 }）—— 文件多半被截断了`);

    /* keyframes 光配平还不够：只剩 0% 帧照样「合法」，动画却是死的。 */
    for (const m of css.matchAll(/@keyframes\s+([\w-]+)\s*\{/g)) {
      let i = m.index + m[0].length, d = 1;
      while (i < css.length && d > 0) { if (css[i] === "{") d++; else if (css[i] === "}") d--; i++; }
      const body = css.slice(m.index + m[0].length, i - 1);
      const stops = [...body.matchAll(/(^|[\s,{}])(from|to|\d+(?:\.\d+)?%)\s*[,{]/g)].map((s) => s[2]);
      assert.ok(stops.length >= 2,
        `${f}：@keyframes ${m[1]} 只有 ${stops.length} 个关键帧（${stops.join("/") || "一个都没有"}）—— 少一头就是不动`);
    }
  }
});

/* ★ 0902 补的，起因是这次真出的事故：
   同一片枫叶（Font Awesome canadian-maple-leaf）在仓库里存了**两份不同的 path**——
   `base/crest.js` 是 384×512 的变体（叶柄脚 x=208.6..238.6），
   `glyphcloud/glyph-cloud.js` 是 512×512 的（叶柄脚 x=241..271）。
   而「通话那条线」找叶柄用的是写死的 (241,512)/(271,512)，照 512 那份量的。
   喂 crest 那份进去 → 两个锚点落到同一个采样点 → 整片轮廓只取回 1 个点 →
   **「在想」那一段一片叶子都写不出来**，而且不报错、不警告，只是叶子不见了。

   为什么不做成「只留一份，别的都 import 它」：每块要能被单独拿走
   （零依赖是这个包的硬承诺），互相 import 就毁了这一条。
   所以留副本，但**用测试钉死它们一模一样** —— 谁改了一处，这条就红。 */
test("★ 全仓库只许有一片枫叶（副本必须逐字相同）", async () => {
  const repo = dirname(root);
  const SKIP = new Set(["node_modules", "dist", ".git", ".venv", "build", ".gradle"]);
  const MAPLE = /M383\.8 351\.7[^"']*/g;
  const found = new Map();                       /* path 原文 → [出现在哪些文件] */

  const walk = async (dir) => {
    let ents;
    try { ents = await readdir(dir, { withFileTypes: true }); } catch { return; }
    for (const e of ents) {
      if (e.name.startsWith(".") || SKIP.has(e.name) || e.name.includes(".bak")) continue;
      const p = join(dir, e.name);
      if (e.isDirectory()) { await walk(p); continue; }
      if (!/\.(js|html|css|svg)$/.test(e.name)) continue;
      let src; try { src = await readFile(p, "utf8"); } catch { continue; }
      for (const m of src.match(MAPLE) || []) {
        found.set(m, [...(found.get(m) || []), p.slice(repo.length + 1)]);
      }
    }
  };
  await walk(repo);

  assert.ok(found.size > 0, "一片枫叶都没找到 —— 这条测试自己坏了");
  if (found.size > 1) {
    const report = [...found.entries()]
      .map(([d, files], i) => `  版本${i + 1}（${d.length} 字节）：${files.join("、")}`)
      .join("\n");
    assert.fail(`枫叶漂开了，出现 ${found.size} 个不同版本：\n${report}\n` +
      "★ 以 blocks/base/crest.js 那份为准，把别处改回来。别在这儿留第二份。");
  }
});
