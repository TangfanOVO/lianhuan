/* 取件器 —— 按 lianhuan.layers.json 把某一块连着它的依赖，整齐地取到仓库外面去。
   ════════════════════════════════════════════════════════════════════
     node scripts/take-pack.mjs --list
     node scripts/take-pack.mjs frontend/ambience /absolute/new-folder

   零依赖，node 20+。

   四道防覆盖的闸（顺序是硬的，越靠前越便宜）：
     ① 目标必须是绝对路径 —— 相对路径最容易把副本生在源码树里
     ② 目标不能在本仓内部
     ③ 目标**必须还不存在** —— 绝不往已有目录里倒东西
     ④ 中途任何一步出错，整个目标目录删掉重来，不留半截

   许可怎么定：把这一次带上的每条的 license 收成一个集合。
   **全是 MIT 就给 MIT；只要混进一条 AGPL，根许可就是 AGPL。**
   —— 宽的那个不能盖住严的那个，反过来可以。 */
import { access, cp, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const catalog = JSON.parse(await readFile(join(root, "lianhuan.layers.json"), "utf8"));
const groups = {
  function: catalog.functionPacks,
  frontend: catalog.frontendPacks,
  profile: catalog.profiles,
};

/* 不管取什么，这几样都跟着走 —— 许可、第三方声明、清单本体和它的说明 */
const scaffold = ["LICENSE", "THIRD_PARTY_NOTICES.md", "lianhuan.layers.json",
                  "docs/lianhuan-layers.schema.json", "docs/PACKS.md"];

/* ★ 只要带走了 blocks/ 底下任何一块，这个包自己的那套骨架就得跟着 ——
   不然副本里有源码却没有 package.json、没有 LICENSE、没有 build 和 test，
   `npm install` 当场 enoent。（第一次真取就是这么炸的，所以有了这几行。） */
const blocksScaffold = ["blocks/package.json", "blocks/LICENSE", "blocks/README.md",
                        "blocks/scripts", "blocks/tests"];

/* ★ 这三类一个都不许复制。前两类是安全，第三类是别人机器上重新生成就有的东西。 */
const blockedDirs = new Set([".git", ".venv", "node_modules", "dist", "build", "coverage",
                             ".gradle", "__pycache__", ".pytest_cache", "data", "my-home", "files"]);
const blockedExt = new Set([".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3", ".dump",
                            ".jks", ".keystore", ".key", ".pem", ".p12", ".mobileprovision",
                            ".pyc", ".log", ".enc"]);
const blockedNames = new Set([".env", ".env.local", ".DS_Store", "local.properties",
                              "secrets.json", ".npmrc", ".netrc", "auth.json", "cookies.json",
                              "AGENTS.md"]);

function die(msg) {
  console.error("\n取件没成：" + msg + "\n");
  process.exitCode = 1;
}

function resolveRef(ref) {
  const [g, id, extra] = String(ref).split("/");
  if (extra || !g || !id || !(g in groups)) return null;
  const item = groups[g]?.[id];
  return item ? { ref, group: g, id, item } : null;
}

function printList() {
  const head = { function: "功能", frontend: "外观 · 交互 · 前端", profile: "组合方案" };
  for (const [g, items] of Object.entries(groups)) {
    console.log("\n" + head[g]);
    for (const [id, it] of Object.entries(items)) {
      const tail = it.takeable === false ? "  （整仓，直接 clone）"
                 : it.license === "MIT" ? "  （MIT）" : "";
      console.log("  " + (g + "/" + id).padEnd(30) + it.label + tail);
      console.log("      " + it.summary);
    }
  }
  console.log("\n取一块：node scripts/take-pack.mjs frontend/ambience /absolute/new-folder\n");
}

/* 依赖闭包。深度优先＋环检测 —— 环不报出来的话，取件器会静静地栈溢出。 */
function closure(start) {
  const done = new Set(), doing = new Set(), out = [];
  (function visit(ref) {
    if (done.has(ref)) return;
    if (doing.has(ref)) throw new Error("依赖成环了：" + ref);
    const r = resolveRef(ref);
    if (!r) throw new Error("清单里没有 " + ref);
    doing.add(ref);
    for (const dep of r.item.requires || []) visit(dep);
    doing.delete(ref);
    done.add(ref);
    out.push(r);
  })(start);
  return out;
}

/* 去掉被别的路径包住的那些 —— 不然 blocks 和 blocks/base 会各拷一遍 */
function tidyPaths(items) {
  const raw = items.flatMap(({ item }) => [...(item.paths || []), ...(item.docs || [])]);
  const needBlocks = raw.some((p) => p === "blocks" || p.startsWith("blocks/"));
  const all = [...new Set(raw.concat(scaffold, needBlocks ? blocksScaffold : []))]
    .filter((p) => p && p !== ".")
    .map((p) => p.replaceAll("\\", "/").replace(/^\.\//, ""));
  return all.filter((p) => !all.some((parent) => parent !== p && p.startsWith(parent + "/")));
}

function keep(src) {
  const rel = relative(root, src);
  if (rel.split(sep).some((seg) => blockedDirs.has(seg))) return false;
  const name = basename(src);
  if (blockedNames.has(name)) return false;
  if (name.startsWith(".env.") && name !== ".env.example") return false;
  if (/\.bak/.test(name)) return false;                 // 备份里是没清洗过的旧版本
  if (/^REVIEW-.*\.md$/.test(name)) return false;       // 验收报告里有本机路径当证据
  const dot = name.lastIndexOf(".");
  if (dot > 0 && blockedExt.has(name.slice(dot))) return false;
  return true;
}

const there = async (p) => { try { await access(p); return true; } catch { return false; } };

async function copyOne(rel, target) {
  const from = join(root, rel);
  if (!(await there(from))) throw new Error("清单指向了不存在的路径：" + rel);
  const to = join(target, rel);
  await mkdir(dirname(to), { recursive: true });
  if ((await stat(from)).isDirectory()) await cp(from, to, { recursive: true, filter: keep });
  else if (keep(from)) await cp(from, to);
}

/* 带上的东西里有没有 Python / 有没有那个前端积木包 —— 决定生成什么运行清单 */
async function shapeOf(target, paths) {
  const hasBlocks = await there(join(target, "blocks", "package.json"));
  let hasPy = false;
  const walk = async (d) => {
    for (const e of await readdir(d, { withFileTypes: true })) {
      if (hasPy) return;
      const p = join(d, e.name);
      if (e.isDirectory()) await walk(p);
      else if (e.name.endsWith(".py")) hasPy = true;
    }
  };
  await walk(target).catch(() => {});
  const hasAndroid = paths.some((p) => p === "android" || p.startsWith("android/"));
  return { hasBlocks, hasPy, hasAndroid };
}

/* 把副本里的 blocks/package.json 裁短：只留这次真带过来的那些 export。
   ★ 不裁的话，build 和 test 会去找根本没复制过来的文件。 */
async function narrowBlocks(target) {
  const p = join(target, "blocks", "package.json");
  if (!(await there(p))) return false;
  const pkg = JSON.parse(await readFile(p, "utf8"));
  const kept = {};
  for (const [name, rel] of Object.entries(pkg.exports || {}))
    if (await there(join(target, "blocks", rel))) kept[name] = rel;
  pkg.exports = kept;
  await writeFile(p, JSON.stringify(pkg, null, 2) + "\n", "utf8");
  return true;
}

async function writeManifests(target, picked, included, paths) {
  await narrowBlocks(target);
  const licenses = new Set(included.map(({ item }) => item.license).filter(Boolean));
  const license = licenses.size === 1 && licenses.has("MIT") ? "MIT" : catalog.license;
  const { hasBlocks, hasPy, hasAndroid } = await shapeOf(target, paths);

  const cmds = [];
  if (hasBlocks) cmds.push(["npm install", "装依赖（这个包零依赖，只是把 npm 那套跑通）"],
                           ["npm run build", "拼出 dist/blocks.css 和各块的 js"],
                           ["npm test", "自检：许可边界、零依赖、零网络、每块都有 demo"]);
  if (hasPy) cmds.push(["python3 -m venv .venv && .venv/bin/pip install -r requirements.txt", "装 Python 依赖"],
                       ["bash start.command", "起服务"]);

  if (hasBlocks) {
    const slug = picked.ref.replaceAll("/", "-").replace(/[^a-z0-9-]/gi, "-").toLowerCase();
    await writeFile(join(target, "package.json"), JSON.stringify({
      name: "lianhuan-takeaway-" + slug,
      private: true, version: "0.1.0", license, type: "module",
      workspaces: ["blocks"],
      scripts: {
        build: "npm run build -w lianhuan-blocks",
        test: "npm test -w lianhuan-blocks",
      },
    }, null, 2) + "\n", "utf8");
  }

  /* 根许可：全 MIT 就把积木那份 MIT 抬上来，否则留仓库那份 AGPL */
  if (license === "MIT" && await there(join(target, "blocks", "LICENSE"))) {
    await cp(join(target, "blocks", "LICENSE"), join(target, "LICENSE"));
  }

  const imports = [...new Set(included.flatMap(({ item }) => item.imports || []))];
  const lines = (xs, empty) => xs.length ? xs.map((x) => "- `" + x + "`").join("\n") : empty;
  const md = `# ${picked.item.label}

这是照 \`lianhuan.layers.json\` 取出来的一份最小工作区。
选的是 \`${picked.ref}\`，它要的东西已经自动跟着来了。

## 先跑起来

${cmds.length ? "```bash\n" + cmds.map(([c]) => c).join("\n") + "\n```\n\n"
  + cmds.map(([c, why]) => "- `" + c + "` —— " + why).join("\n")
  : "这一份是源码，没有构建步骤。直接读、直接改。"}

## 带上了什么

${included.map(({ ref, item }) => `- \`${ref}\` — ${item.label}\n  - ${item.truth}`).join("\n")}

## 能直接引的路径

${lines(imports, "- 这一份没有独立的引入路径，按目录里的用法接。")}

## 留下的源码路径

${paths.map((p) => "- `" + p + "`").join("\n")}

## 许可

这一份是 **${license}**。

${license === "MIT"
  ? "带上的全是纯前端积木，所以整份按 MIT 给你。\n完整的连环应用仍然是 AGPL-3.0-only —— 只有被单独标成 MIT 的那些块可以这样带走。"
  : "里头混了完整应用的源码，所以整份按 AGPL-3.0-only。\n改了它、拿去做成网络服务给别人用，就要把改动后的完整源码交出来。"}

第三方组件保留它们各自的许可与署名，见 \`THIRD_PARTY_NOTICES.md\` —— 整仓是什么许可，
都不会把上游那些改掉。

## 边界

- 取件器不复制：\`.env\`、密钥与证书、数据库与真实聊天、登录态、
  \`node_modules\` / \`dist\` / \`build\` / 缓存、备份文件、验收报告。
- 带了界面**不等于**已经接通模型、语音或任何外部服务 —— 每条上面写的 \`truth\` 才算数。
- 继续往外分发的时候，把这份许可和第三方说明一起带上。
${hasAndroid ? "- 安卓那部分只能说「壳构建得出来」；没有真机逐项点过之前，别写成「安卓全功能已验收」。\n" : ""}`;
  await writeFile(join(target, "TAKEAWAY.md"), md, "utf8");
  return { license, cmds };
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && (args[0] === "--list" || args[0] === "list")) return printList();
  if (args.length !== 2)
    throw new Error("用法：node scripts/take-pack.mjs <function|frontend|profile>/<id> /absolute/new-folder");

  const [ref, targetArg] = args;
  const picked = resolveRef(ref);
  if (!picked) throw new Error("清单里没有 " + ref + "；先跑一次 --list 看有哪些");
  if (picked.item.takeable === false)
    throw new Error(ref + " 就是整仓 —— 直接 clone，别再生成第二份副本");
  if (!isAbsolute(targetArg)) throw new Error("目标必须是绝对路径，免得副本生在源码树里");
  const target = resolve(targetArg);
  if (target === root || target.startsWith(root + sep)) throw new Error("目标不能在本仓内部");
  if (await there(target)) throw new Error("目标已经存在了；换一个全新的空路径，别覆盖任何东西");

  const included = closure(ref);
  const paths = tidyPaths(included);
  await mkdir(target, { recursive: false });
  let info;
  try {
    for (const p of paths) await copyOne(p, target);
    info = await writeManifests(target, picked, included, paths);
  } catch (e) {
    await rm(target, { recursive: true, force: true });     // 半截的副本比没有更坏
    throw e;
  }

  console.log("\n取好了：" + picked.item.label);
  console.log("  去处：" + target);
  console.log("  带上：" + included.map((x) => x.ref).join("、"));
  console.log("  许可：" + info.license);
  console.log("  下一步：cd " + target + (info.cmds.length ? " && " + info.cmds[0][0] : ""));
  console.log("  这一份能干什么、不能干什么，都写在 TAKEAWAY.md 里了\n");
}

main().catch((e) => die(e instanceof Error ? e.message : String(e)));
