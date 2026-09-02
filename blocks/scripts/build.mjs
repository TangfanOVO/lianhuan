/* 把这个包里**现有的**积木拼成一份 dist —— 零依赖，就 node 自带的 fs。
   ★ 为什么不上打包器：这些块本来就是零依赖的纯 CSS/JS，为了「有个 build」
     拖进一个 bundler，正好是这个项目最不想干的事。这儿只做三件：拼 CSS、拷 JS、写清单。
   ★ 清单从 package.json 的 exports 里读，**不写死列表** ——
     取件器会按取走了哪几块把 exports 裁短，写死的话裁完就对不上了。 */
import { mkdir, readFile, writeFile, rm, cp, access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, "dist");
const pkg = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
const there = async (p) => { try { await access(join(root, p)); return true; } catch { return false; } };

const all = Object.values(pkg.exports || {});
const css = [], js = [];
for (const rel of all) {
  if (!(await there(rel))) continue;
  (rel.endsWith(".css") ? css : js).push(rel);
}
/* 样式里还有几份不是 export 出去的（同一块的附属样式），一起拼上 */
for (const extra of ["physics/paper-stack.css", "robot/robot.css", "glyphcloud/glyph-cloud.css"])
  if (!css.includes(extra) && await there(extra)) css.push(extra);
css.sort();

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

let out = "/* 连环前端积木 · MIT · 见 LICENSE */\n";
for (const f of css) out += `\n/* ── ${f} ── */\n` + await readFile(join(root, f), "utf8");
await writeFile(join(dist, "blocks.css"), out, "utf8");

for (const f of js) {
  const to = join(dist, f);
  await mkdir(dirname(to), { recursive: true });
  await cp(join(root, f), to);
}
/* 机器人那块的数据层不在 exports 里，但它是同一块的一半 */
if (js.some((f) => f.startsWith("robot/")) && await there("robot/robot-data.js")) {
  await mkdir(join(dist, "robot"), { recursive: true });
  await cp(join(root, "robot/robot-data.js"), join(dist, "robot/robot-data.js"));
}
if (await there("LICENSE")) await cp(join(root, "LICENSE"), join(dist, "LICENSE"));

const bytes = Buffer.byteLength(out, "utf8");
await writeFile(join(dist, "manifest.json"),
  JSON.stringify({ css: "blocks.css", cssBytes: bytes, js, license: pkg.license }, null, 1) + "\n", "utf8");
console.log(`拼好了：dist/blocks.css ${(bytes / 1024).toFixed(1)} KB · ${js.length} 个 js · LICENSE 一起带上`);
