/* 生成一份干净的公开候选 —— 从源码现做一份，不是把工作树改一改。
   ════════════════════════════════════════════════════════════════
     node scripts/prepare-public-copy.mjs /absolute/new-folder

   两条纪律：
   ① **白名单，不是黑名单。** 顶层只复制列在下面的那些，
      新加的东西默认**不**出门 —— 「忘记排除」这个错误从结构上就不成立了。
   ② **自己检查自己。** 副本做完立刻用副本里那支扫描器以发布档扫一遍，
      不过就把整个副本删掉再报错 —— 半干净的副本比没有更危险，
      因为它看起来像是能发的。 */
import { execFile } from "node:child_process";
import { access, cp, mkdir, readdir, rm } from "node:fs/promises";
import { basename, dirname, extname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";

const runFile = promisify(execFile);
const source = resolve(fileURLToPath(new URL("..", import.meta.url)));

/* 顶层白名单。想让什么出门，得在这儿写上名字。 */
const allowTop = new Set([
  ".env.example", ".gitignore",
  ".github",                    /* 0902：Pages 的 Actions 流程在里头，不放行就发不了 */
  "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "UPSTREAM.md", "EXCLUDED.md",
  "lianhuan.layers.json", "package.json",
  "android", "app", "apps", "blocks", "core", "docs", "examples", "optional",
  "scripts", "seed", "tests", "tools",
  "create.py", "requirements.txt", "start.command", "start.sh",
]);

/* 上面放行的目录里，这些还是要挡 */
const skipNames = new Set([".DS_Store", "local.properties", "secrets.json",
                           ".env", ".npmrc", ".netrc", "auth.json", "cookies.json"]);
const skipDirs = new Set([".git", ".venv", "node_modules", "dist", "build", "coverage",
                          ".gradle", "__pycache__", ".pytest_cache", "data", "my-home", "files"]);
const skipExt = new Set([".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3", ".dump", ".enc",
                         ".jks", ".keystore", ".key", ".pem", ".p12", ".mobileprovision",
                         ".pyc", ".log"]);

function include(path) {
  const name = basename(path);
  if (skipNames.has(name) || skipDirs.has(name)) return false;
  if (name.startsWith(".env.") && name !== ".env.example") return false;
  if (/\.bak/.test(name)) return false;                  // 备份里是没清洗过的旧版本
  if (/^REVIEW-.*\.md$/.test(name)) return false;        // 验收报告里有本机路径当证据
  if (name === "AGENTS.md") return false;                // 给验收 agent 的交接，它自己说了要删
  return !skipExt.has(extname(name).toLowerCase());
}

const there = async (p) => { try { await access(p); return true; } catch { return false; } };

export async function preparePublicCopy(targetValue) {
  if (!targetValue) throw new Error("给一个还不存在的绝对路径当目标");
  const target = resolve(targetValue);
  if (!isAbsolute(target) || target === source || target.startsWith(source + "/"))
    throw new Error("目标必须在源码目录外面");
  if (await there(target)) throw new Error("目标已经存在了：" + target);

  await mkdir(dirname(target), { recursive: true });
  await mkdir(target, { recursive: false });
  for (const e of await readdir(source, { withFileTypes: true })) {
    if (!allowTop.has(e.name)) continue;
    /* ★ verbatimSymlinks：不加这个，node 会把软链接的目标**重写成源目录的绝对路径** ——
       副本里的 start.sh 就指回了我这台机器上的源码树，
       拿到别人手里是死链，而且顺带漏出本机用户名。
       （这一条是副本自检当场抓出来的，不是想出来的。） */
    await cp(join(source, e.name), join(target, e.name),
             { recursive: true, filter: include, verbatimSymlinks: true });
  }

  try {
    await runFile(process.execPath,
      [join(target, "scripts/check-public-boundary.mjs"), "--root", target],
      { cwd: target, env: { ...process.env, PUBLIC_RELEASE: "1" } });
  } catch (cause) {
    const why = (cause?.stdout || "") + (cause?.stderr || "") || String(cause);
    await rm(target, { recursive: true, force: true });
    throw new Error("这份副本没过公开边界，已经整个删掉了：\n" + why.trim());
  }
  return target;
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const t = await preparePublicCopy(process.argv[2]);
  console.log("干净的公开候选做好了：" + t);
  console.log("下一步：进去跑一遍全套（测试 / checkhtml / 两份 HTML 一致 / create.py 出产物），再谈发布。");
}
