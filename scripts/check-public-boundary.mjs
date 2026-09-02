/* 公开边界检查 —— 这一份要能公开出去的东西里，有没有不该出去的。
   ════════════════════════════════════════════════════════════════
   零依赖，node 20+ 就能跑。两种模式：

     node scripts/check-public-boundary.mjs                    # 普通：查形状
     LIANHUAN_PRIVATE_MARKERS="…" PUBLIC_RELEASE=1 \
       node scripts/check-public-boundary.mjs                  # 发布前：再查具体的词

   ★ 为什么分两种模式：
     「查形状」能查密钥长什么样、绝对路径长什么样、数据库是什么后缀 —— 这些不需要知道
     任何具体的私人信息，所以规则可以公开放在仓库里。
     但「这个仓库里不许出现哪几个名字」这种事，规则本身就是私人信息 ——
     写进仓库等于把要藏的东西列了个清单贴在门口。
     所以那一类词**从环境变量传进来**，一个字都不留在代码里。

   退出码 0 = 干净；1 = 有东西不该出去（每条带路径和原因，但**不回显命中的原文**）。 */
import { lstat, readdir, readFile, readlink, stat } from "node:fs/promises";
import { extname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootArg = process.argv[2] === "--root" ? process.argv[3] : "";
const root = resolve(rootArg || fileURLToPath(new URL("..", import.meta.url)));   // resolve 会把结尾斜杠去掉
if (rootArg && !isAbsolute(root)) throw new Error("扫描根必须是绝对路径");
const release = process.env.PUBLIC_RELEASE === "1";
/* ★ 两种用法，别混：
   · 默认（不带 --worktree）＝ 扫**待发布的那一份**。任何一条命中都是失败。
   · --worktree ＝ 扫**手头这棵工作树**。`.bak*` / 验收报告 / AGENTS.md 这些
     .gitignore 本来就挡着，发布副本里根本不会有 —— 报一声让人看见，但不算失败。
     （不把它们整个跳过：万一哪天 .gitignore 漏了，这一行就是唯一的提示。） */
const worktree = process.argv.includes("--worktree");

/* 这些目录整个不看：要么是构建出来的，要么是本机的东西 */
const skipDirs = new Set([
  ".git", ".venv", "node_modules", "__pycache__", "dist", "build", "coverage", ".gradle", ".pytest_cache",
]);
const skipDirPaths = [
  /^data$/,                       // 使用者自己的库和文件，.gitignore 里也挡着
  /^my-home$/,
  /^files$/,
  /^android(?:\/[^/]+)*\/build$/,
];

/* 这些文件按名字/后缀直接拦 */
const blockedNames = new Set([
  ".env", ".env.local", ".npmrc", ".netrc", "auth.json", "cookies.json", "local.properties",
]);
const blockedExt = new Set([
  ".db", ".sqlite", ".sqlite3", ".dump", ".enc", ".jks", ".keystore", ".key", ".pem", ".p12",
  ".mobileprovision", ".pyc", ".log",
]);

/* 这些是「本地的、发布前要删」的东西 —— 出现在待发布的那一份里就是错 */
const localOnly = [
  /^REVIEW-[^/]*\.md$/,           // 外部验收报告和回执：里面有本机路径当证据
  /^AGENTS\.md$/,                 // 给验收 agent 的交接，它自己说了发布前删
  /(^|\/)[^/]*\.bak[^/]*$/,       // 改前备份：里面是**没清洗过**的旧版本
  /^android\/local\.properties$/, // 安卓 SDK 的本机路径，.gitignore 挡着
];

/* 长得像凭据的 */
const credentialShapes = [
  /-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/,
  /(?:^|[^A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}/,
  /(?:^|[^A-Za-z0-9_-])sk_[A-Za-z0-9]{24,}/,          // 某些语音服务用这个前缀
  /(?:postgres|postgresql|mysql|mongodb(?:\+srv)?):\/\/[^\s"'`]+/i,
  /gh[opsu]_[A-Za-z0-9]{20,}/,
  /AIza[0-9A-Za-z_-]{30,}/,
  /AKIA[0-9A-Z]{16}/,
  /xox[baprs]-[A-Za-z0-9-]{10,}/,
  /eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}/,   // JWT
];

/* 本机路径：拿到别人机器上就是死链，而且会漏出用户名 */
const machinePaths = [
  /\/Users\/[^/\s"'`]+\//,
  /\/home\/(?!runner\/)[^/\s"'`]+\//,     // CI 的 /home/runner 不算
  /\\Users\\[^\\\s"'`]+\\/,
  /\bC:\\Users\\/i,
];

/* 联系方式 */
const contactShapes = [
  /\b[A-Za-z0-9._%+-]+@(?!example\.(?:com|org|net)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/,
  /\b1[3-9]\d{9}\b/,                                            // 手机号
  // ★ IPv4 要有上下文才算 —— 光看形状会把版本号当成 IP
  //   （真栽过：上游模型版本 "1.2.6.1" 被判成联系方式）。
  //   所以只在它前后确实像个地址的时候才报。
  /(?:https?:\/\/|@|\bip\b|\bhost\b|\bserver\b|\bssh\b|\bping\b)[^\n]{0,24}\b(?:\d{1,3}\.){3}\d{1,3}\b/i,
  /\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d{2,5}\b|\s*(?:—|--)?\s*(?:服务器|主机|地址))/,
];
/* 上面那几条太宽，下面这些形状是正常出现的，放行 */
const contactAllow = [
  /\b(?:0\.0\.0\.0|127\.0\.0\.1|255\.255\.255\.255|1\.2\.3\.4|0\.1\.2\.3)\b/,
  /\b(?:\d{1,3}\.){3}\d{1,3}\b(?=\s*(?:—|--|、|,)?\s*(?:示例|example))/i,
];

/* 不看内容的二进制/字体/图片 */
const binaryExt = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".otf",
  ".mp3", ".wav", ".m4a", ".mp4", ".zip", ".gz", ".tar", ".jar", ".so", ".dylib",
]);
/* 但二进制也不是随便放的 —— 只有过过目的才准留 */
const reviewedBinaries = [
  /^core\/web\/icons\/icon-(?:180|192|512|512-maskable)\.png$/,
  /^core\/web\/favicon\.ico$/,
  /^android\/app\/src\/main\/(?:res\/(?:mipmap|drawable)[^/]*|assets\/public)\/[^/]+\.(?:png|xml|webp)$/,
  /^android\/gradle\/wrapper\/gradle-wrapper\.jar$/,
  /\.svg$/,                       // 图标是我们自己画的向量，扫内容那一遍会看到它
];

const SIZE_CAP = 2_000_000;

/* 发布前那一遍要查的具体词，从环境变量来，一个字不留在仓库里 */
const markers = (process.env.LIANHUAN_PRIVATE_MARKERS ?? "")
  .split(",").map((s) => s.trim()).filter(Boolean);

const bad = [];
const local = [];
const files = [];

if (release && markers.length === 0) {
  bad.push("发布模式要 LIANHUAN_PRIVATE_MARKERS —— 那一串词不许写进仓库，发布时从环境变量传进来");
}

function rel(p) { return relative(root, p).replaceAll("\\", "/"); }

async function walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    const r = rel(p);
    if (e.isDirectory() && (skipDirs.has(e.name) || skipDirPaths.some((x) => x.test(r)))) continue;
    if ((await lstat(p)).isSymbolicLink()) {
      // 指向仓库里面的软链接是正常的（start.sh → start.command）；指到外面才危险
      const to = resolve(dir, await readlink(p));
      if (to !== root && !to.startsWith(root + "/")) { bad.push(`${r}：软链接指到了仓库外面`); continue; }
    }
    if (e.isDirectory()) await walk(p);
    else if (e.isFile()) files.push(p);
  }
}

await walk(root);

for (const p of files) {
  const r = rel(p);
  const name = r.split("/").at(-1);
  const ext = extname(name).toLowerCase();

  if (localOnly.some((x) => x.test(r))) {
    (worktree ? local : bad).push(`${r}：本地的东西，发布不带（备份 / 验收报告 / 给 agent 的交接）`);
    continue;
  }
  if (blockedNames.has(name) || blockedExt.has(ext)) { bad.push(`${r}：这类文件不许出门`); continue; }
  if ((await stat(p)).size > SIZE_CAP) { bad.push(`${r}：超过 2 MB，太大的东西要人过一遍眼`); continue; }

  if (binaryExt.has(ext)) {
    if (!reviewedBinaries.some((x) => x.test(r))) { bad.push(`${r}：没过目的二进制/图片`); continue; }
    if (ext !== ".svg") continue;                 // svg 是文本，接着往下扫内容
  }

  let text;
  try { text = await readFile(p, "utf8"); } catch { bad.push(`${r}：读不成文本，也不在放行名单里`); continue; }

  if (credentialShapes.some((x) => x.test(text))) bad.push(`${r}：有一段长得像密钥`);
  if (machinePaths.some((x) => x.test(text))) bad.push(`${r}：写着本机绝对路径`);
  for (const line of text.split("\n")) {
    if (contactAllow.some((x) => x.test(line))) continue;
    if (contactShapes.some((x) => x.test(line))) { bad.push(`${r}：有一段长得像联系方式（邮箱/手机号/IP）`); break; }
  }
  for (const m of markers) if (text.includes(m)) { bad.push(`${r}：命中了发布前那张词表`); break; }
}

if (local.length) {
  console.log(`\n工作树里有 ${local.length} 个本地件（.gitignore 挡着，发布副本里不会有）：`);
  const head = [...new Set(local)].slice(0, 6);
  for (const x of head) console.log(`  · ${x}`);
  if (local.length > head.length) console.log(`  · …还有 ${local.length - head.length} 个`);
}
if (bad.length) {
  console.error(`\n公开边界没过（扫了 ${files.length} 个文件）：\n` + [...new Set(bad)].map((x) => `  - ${x}`).join("\n") + "\n");
  process.exitCode = 1;
} else {
  console.log(`\n公开边界干净：扫了 ${files.length} 个文件${release ? "（发布模式，词表也查了）" : ""}${worktree ? "（工作树模式）" : ""}。`);
}
