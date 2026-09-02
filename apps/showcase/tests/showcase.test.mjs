/* 预览站的自检。★ 钉的都是**承诺**：这一页说自己不碰什么，就真的不许碰。 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));
const html = await readFile(join(here, "index.html"), "utf8");
const js = await readFile(join(here, "showcase.js"), "utf8");
const css = await readFile(join(here, "showcase.css"), "utf8");
const pkg = JSON.parse(await readFile(join(here, "package.json"), "utf8"));
const there = async (p) => { try { await access(join(here, p)); return true; } catch { return false; } };

test("是 MIT，LICENSE 在，零依赖", async () => {
  assert.equal(pkg.license, "MIT");
  assert.ok(await there("LICENSE"));
  for (const f of ["dependencies", "peerDependencies"]) assert.equal(pkg[f], undefined);
});

test("★ 不碰真数据、不连模型、不要权限", () => {
  const all = html + js;
  for (const bad of ["getUserMedia", "MediaRecorder", "Notification.request",
                     "geolocation", "indexedDB", "localStorage", "sessionStorage",
                     "/api/", "EventSource", "new WebSocket"]) {
    assert.ok(!all.includes(bad), `预览站里出现了 ${bad} —— 它承诺过不碰这些`);
  }
});

test("★ 不发外部请求（p5 那一条是块自己带的，且已标出来）", () => {
  /* ★ 0902：REPO 那一行是「看源码」的 href，不是这一页发出去的请求 —— 剥掉再查。 */
  const jsNoRepo = js.replace(/var REPO = "[^"]*";/, 'var REPO = "";');
  const urls = [...(html + jsNoRepo + css).matchAll(/https?:\/\/[^\s"'`)]+/g)].map((m) => m[0]);
  assert.deepEqual(urls, [], "预览站自己不该引任何外链：" + urls.join("、"));
  assert.ok(js.includes("会发一次外部请求") || js.includes("外部请求"),
            "水面那块要 p5，得在页面上标出来");
});

test("★ 「看源码」不许指向本机", () => {
  const repo = /var REPO = "(.*?)"/.exec(js)[1];
  for (const bad of ["localhost", "127.0.0.1", "file://", "/Users/", "/home/"])
    assert.ok(!repo.includes(bad), "REPO 指向了本机：" + repo);
});

test("★ 页脚两种许可都要写清楚", () => {
  assert.ok(html.includes("MIT"), "前端积木是 MIT，要写");
  assert.ok(html.includes("AGPL-3.0-only"), "完整应用是 AGPL-3.0-only，要写");
});

test("★ 预览数据要标明是编的", () => {
  assert.ok(html.includes("编的") && html.includes("刷新就没"), "得说清这些字是假的、刷新就没");
  /* ★ 0902 改：原来这儿查的是 `js.includes("预览数据")` —— 那是预览站里**手写的假聊天**
     抬头上的字。那块假骨架已经退役（聊天现在是 blocks/chat/ 整段搬来的真页面），
     所以改成查**每一块的说明里都得交代清楚它演的是什么**。 */
  const truths = [...js.matchAll(/truth:\s*((?:"[^"]*"\s*\+?\s*)+)/g)].map((m) => m[1]);
  assert.ok(truths.length >= 8, "面板说明少了，只数到 " + truths.length + " 条");
  for (const key of ["编的", "不连模型", "不申请麦克风"])
    assert.ok(js.includes(key), `面板说明里没交代「${key}」`);
});

/* ★ 0902 换掉了「假骨架的 class 一律 fake- 开头」那条。
   那条防的是「预览站里手写的仿制品被误当成积木」—— 现在一块仿制品都不剩，
   防的东西不存在了。换成正面钉死这件事：**这一页不许自己画任何一块的样子**。 */
test("★ 这一页不许自己画任何一块的样子", () => {
  assert.ok(!js.includes("fakeChat") && !js.includes("self-demo"),
            "又出现手写的仿制品了 —— 每块只能用它自己那份 demo");
  const srcs = [...js.matchAll(/demo:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(srcs.length >= 8, "面板少了，只数到 " + srcs.length + " 块");
  for (const s of srcs) assert.match(s, /^[a-z-]+\/demo[a-z-]*\.html$/, "demo 路径不对：" + s);
  /* 每块都必须真的有 demo 文件在 */
});

test("★ 每块登记的 demo 文件真的在", async () => {
  const blocks = join(here, "..", "..", "blocks");
  const srcs = [...js.matchAll(/demo:\s*"([^"]+)"/g)].map((m) => m[1]);
  for (const s of srcs) {
    try { await access(join(blocks, s)); }
    catch { assert.fail(`登记了 ${s}，但 blocks/${s} 不存在`); }
  }
});

test("每块都给了取件命令", () => {
  const packs = [...js.matchAll(/pack:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(packs.length >= 9, "面板少了：" + packs.length);
  for (const p of packs) assert.match(p, /^(function|frontend|profile)\/[a-z-]+$/);
});

test("★ 返回键要能用", () => {
  assert.ok(js.includes("hashchange"),
            "只在启动时读一次 hash 的话，按返回地址变了页面不变，看着就像返回键坏了");
});
