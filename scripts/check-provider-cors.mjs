/* README 里写着「浏览器版可以直接连这几家」—— 那句话得站得住。
   这支脚本对每一家发一次 CORS 预检，看它到底让不让浏览器直连。

     node scripts/check-provider-cors.mjs

   ★ 它**不当门禁**：这是别人家服务器的行为，今天让明天可能就不让，
     为这个把发布卡住不合适。CI 里跑它只是「变了要有人知道」。
   ★ 不带任何 key：预检本来就不需要，也不该在这种脚本里出现。 */
const ORIGIN = "https://tangfanovo.github.io";

const PROVIDERS = [
  ["DeepSeek", "https://api.deepseek.com/chat/completions"],
  ["OpenAI", "https://api.openai.com/v1/chat/completions"],
  ["智谱", "https://open.bigmodel.cn/api/paas/v4/chat/completions"],
  ["硅基流动", "https://api.siliconflow.cn/v1/chat/completions"],
  ["OpenRouter", "https://openrouter.ai/api/v1/chat/completions"],
  ["Kimi", "https://api.moonshot.cn/v1/chat/completions"],
];

const rows = [];
for (const [name, url] of PROVIDERS) {
  let allowed = false, note = "";
  try {
    const r = await fetch(url, {
      method: "OPTIONS",
      headers: {
        origin: ORIGIN,
        "access-control-request-method": "POST",
        "access-control-request-headers": "authorization,content-type",
      },
      signal: AbortSignal.timeout(15000),
    });
    const acao = r.headers.get("access-control-allow-origin") || "";
    allowed = acao === "*" || acao === ORIGIN;
    note = `${r.status} ${acao || "（没给 allow-origin）"}`;
  } catch (e) {
    note = "连不上：" + (e.message || e);
  }
  rows.push({ name, allowed, note });
  console.log(`${allowed ? "可以直连" : "不能直连"}  ${name.padEnd(10)} ${note}`);
}

const claimed = ["DeepSeek", "OpenAI", "智谱", "硅基流动", "OpenRouter"];   // README 里点名的那几家
const broken = rows.filter((r) => claimed.includes(r.name) && !r.allowed);
if (broken.length) {
  console.log("\n⚠ README 说这几家能浏览器直连，现在不行了：" + broken.map((b) => b.name).join("、"));
  console.log("  改文档，别让人照着试了才发现。");
}
