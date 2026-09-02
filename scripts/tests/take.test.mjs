/* 取件器的闸门。每一条都对应一种「会把别人东西弄坏」的取法。 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const take = join(root, "scripts", "take-pack.mjs");
const there = async (p) => { try { await access(p); return true; } catch { return false; } };

async function tryTake(...args) {
  try { return { ok: true, out: (await run(process.execPath, [take, ...args])).stdout }; }
  catch (e) { return { ok: false, out: (e.stdout || "") + (e.stderr || "") }; }
}
const fresh = async (name) => join(await mkdtemp(join(tmpdir(), "lh-take-")), name);

test("--list 把三组都列出来", async () => {
  const { ok, out } = await tryTake("--list");
  assert.ok(ok);
  for (const s of ["功能", "外观", "组合方案", "frontend/ambience"]) assert.ok(out.includes(s), "少了 " + s);
});

test("★ 目标必须是绝对路径", async () => {
  const { ok, out } = await tryTake("frontend/ambience", "relative/path");
  assert.equal(ok, false); assert.ok(out.includes("绝对路径"));
});

test("★ 目标不能在本仓内部", async () => {
  const { ok, out } = await tryTake("frontend/ambience", join(root, "inside"));
  assert.equal(ok, false); assert.ok(out.includes("本仓内部"));
  assert.equal(await there(join(root, "inside")), false, "拒绝之后不许留下痕迹");
});

test("★ 目标已存在就拒绝，绝不覆盖", async () => {
  const { ok, out } = await tryTake("frontend/ambience", tmpdir());
  assert.equal(ok, false); assert.ok(out.includes("已经存在"));
});

test("整仓那两条拒绝取件", async () => {
  const { ok, out } = await tryTake("profile/full-source", await fresh("x"));
  assert.equal(ok, false); assert.ok(out.includes("直接 clone"));
});

test("清单里没有的名字，报得清楚", async () => {
  const { ok, out } = await tryTake("frontend/nothere", await fresh("x"));
  assert.equal(ok, false); assert.ok(out.includes("--list"));
});

test("★ 全是 MIT 的取件，根许可是 MIT，而且带得动 npm", async () => {
  const t = await fresh("mit");
  const { ok } = await tryTake("frontend/ambience", t);
  assert.ok(ok);
  assert.match(await readFile(join(t, "LICENSE"), "utf8"), /^MIT License/);
  const pkg = JSON.parse(await readFile(join(t, "package.json"), "utf8"));
  assert.equal(pkg.license, "MIT");
  assert.ok(pkg.scripts.build && pkg.scripts.test, "得给出 build 和 test 命令");
  assert.ok(await there(join(t, "blocks", "LICENSE")), "积木自己那份 LICENSE 要跟着走");
  assert.ok(await there(join(t, "TAKEAWAY.md")));
  await rm(dirname(t), { recursive: true, force: true });
});

test("★ 混进应用源码，根许可退回 AGPL", async () => {
  const t = await fresh("mixed");
  const { ok } = await tryTake("frontend/shell", t);
  assert.ok(ok);
  assert.match(await readFile(join(t, "LICENSE"), "utf8"), /AFFERO/);
  await rm(dirname(t), { recursive: true, force: true });
});

test("★ 机密、备份、数据库、验收报告一样都不许跟出去", async () => {
  const t = await fresh("clean");
  const { ok } = await tryTake("profile/local-home", t);
  assert.ok(ok);
  const bad = [];
  const walk = async (d) => {
    const { readdir } = await import("node:fs/promises");
    for (const e of await readdir(d, { withFileTypes: true })) {
      const p = join(d, e.name);
      if (e.isDirectory()) { await walk(p); continue; }
      if (/\.bak/.test(e.name) || /^REVIEW-/.test(e.name) || e.name === "AGENTS.md"
          || /\.(db|sqlite3?|pem|key|jks|keystore|pyc|log)$/.test(e.name)
          || e.name === "secrets.json" || e.name === ".env") bad.push(p.slice(t.length));
    }
  };
  await walk(t);
  assert.deepEqual(bad, [], "这些不该跟出去");
  await rm(dirname(t), { recursive: true, force: true });
});
