/* 清单不会自己腐烂 —— 这几条盯着它。
   ★ 比取件器更早写：清单是唯一真源，它一烂，取件器、文档、预览站一起烂。 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const cat = JSON.parse(await readFile(join(root, "lianhuan.layers.json"), "utf8"));
const groups = { function: cat.functionPacks, frontend: cat.frontendPacks, profile: cat.profiles };
const every = Object.entries(groups).flatMap(([g, items]) =>
  Object.entries(items).map(([id, item]) => ({ ref: `${g}/${id}`, item })));
const there = async (p) => { try { await access(join(root, p)); return true; } catch { return false; } };

test("每条都有 label / summary / truth", () => {
  // label 只要不空就行 —— 「本地账本」四个字是个好名字，不该被长度门槛毙掉。
  // summary 和 truth 才需要下限，那两个字段短了就是敷衍。
  for (const { ref, item } of every) {
    assert.ok(item.label && item.label.trim(), `${ref} 缺 label`);
    for (const f of ["summary", "truth"])
      assert.ok(item[f] && item[f].length >= 8, `${ref} 的 ${f} 太短`);
  }
});

test("★ truth 是必填，而且要说得出「它不是什么」", () => {
  // 写不出「没配外部服务时会怎样」，说明这块边界还没想清楚 —— 那就先别放进清单。
  for (const { ref, item } of every)
    assert.ok(item.truth.length >= 12, `${ref} 的 truth 太敷衍了：${item.truth}`);
});

test("kind 在枚举里", () => {
  const ok = new Set(["standalone", "application-slice", "integration", "complete", "frontend"]);
  for (const { ref, item } of every) assert.ok(ok.has(item.kind), `${ref} 的 kind 不认得：${item.kind}`);
});

test("每个 requires 都解析得出来，而且不成环", () => {
  const seen = new Set();
  const visit = (ref, stack) => {
    assert.ok(!stack.includes(ref), `依赖成环：${[...stack, ref].join(" → ")}`);
    const [g, id] = ref.split("/");
    assert.ok(groups[g]?.[id], `指向了不存在的 ${ref}`);
    if (seen.has(ref)) return;
    seen.add(ref);
    for (const d of groups[g][id].requires || []) visit(d, [...stack, ref]);
  };
  for (const { ref } of every) visit(ref, []);
});

test("★ 每个 paths / docs 在磁盘上真存在", async () => {
  for (const { ref, item } of every)
    for (const p of [...(item.paths || []), ...(item.docs || [])]) {
      if (p === ".") continue;
      assert.ok(await there(p), `${ref} 指向了不存在的路径：${p}`);
    }
});

async function collect(p) {
  const { stat, readdir } = await import("node:fs/promises");
  const st = await stat(p).catch(() => null);
  if (!st) return [];
  if (!st.isDirectory()) return [p];
  const out = [];
  for (const e of await readdir(p, { withFileTypes: true })) {
    if (["node_modules", "dist", "tests", ".git"].includes(e.name)) continue;
    out.push(...await collect(join(p, e.name)));
  }
  return out;
}

test("★ 纯前端积木不许依赖应用那半边", async () => {
  // 许可边界的另一半：MIT 的东西一旦要求 AGPL 的东西才能用，它就不是能单独 MIT 带走的了。
  for (const [id, item] of Object.entries(cat.frontendPacks)) {
    if (item.license !== "MIT") continue;
    for (const dep of item.requires || []) {
      assert.ok(dep.startsWith("frontend/"), `frontend/${id} 是 MIT，却要 ${dep}`);
      const [, depId] = dep.split("/");
      assert.equal(cat.frontendPacks[depId]?.license, "MIT",
                   `frontend/${id} 是 MIT，却依赖了非 MIT 的 ${dep}`);
    }
    /* ★ 不按目录名白名单查（那种写法一加新目录就误报）。
       按规格查：一个 MIT 包必须**自己目录里有 MIT 的 LICENSE**，
       而且它的源码不许从应用那半边 import。 */
    for (const p of item.paths || []) {
      const dir = p.startsWith("blocks/") ? "blocks" : p;
      const lic = await readFile(join(root, dir, "LICENSE"), "utf8").catch(() => "");
      assert.match(lic, /MIT License/,
                   `frontend/${id} 说自己是 MIT，但 ${dir}/ 里没有一份 MIT 的 LICENSE`);
      /* 只查**会被 import 的源码**（.js/.css）。README 和 demo 里出现 `/api/…`
         是在教人「你自己接的时候换成这个」—— 那是文档，不是依赖。 */
      const files = (await collect(join(root, p)))
        .filter((f) => /\.(js|css)$/.test(f) && !/\/demo[^/]*\./.test(f));
      /* ★ 判据看**真调用**，不看字符串出现过 ——
         注释里写一句「数据口径跟 /api/xxx 一致」是在交代来源，不是依赖。
         （第一版就是纯 substring，当场把一行注释判成了越界。） */
      const REACH = [
        [/\bfetch\s*\(\s*["'`]\/api/, "fetch 了应用的接口"],
        [/\b(?:import|require)\s*\(?\s*["'`][^"'`]*\.\.\/\.\.\/(?:core|optional|app)\b/, "import 了应用那半边"],
        [/\bnew\s+EventSource\s*\(\s*["'`]\/api/, "订了应用的 SSE"],
      ];
      for (const f of files) {
        if (/robot/.test(f)) continue;          // 机器人那块明说要接你自己的地址
        const src = await readFile(f, "utf8").catch(() => "");
        for (const [re, why] of REACH)
          assert.ok(!re.test(src),
                    `frontend/${id} 是 MIT，但 ${f.slice(root.length + 1)} ${why}`);
      }
    }
  }
});

test("整仓那两条标了 takeable:false", () => {
  for (const id of ["whole-home", "full-source"])
    assert.equal(cat.profiles[id]?.takeable, false, `profile/${id} 应该拒绝取件，让人直接 clone`);
});

test("顶层许可是最严的那个", () => {
  assert.equal(cat.license, "AGPL-3.0-only");
});
