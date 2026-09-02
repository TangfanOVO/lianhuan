/* Service Worker 的运行时台架 —— 在 node 里把 sw.js 真跑一遍。
 *
 * ★ 为什么要有这个（0831 自查 · 病灶 11）：
 *   原来守 sw.js 的三条测试全是「读源码 + assertIn 某个字样」。实测把整个 fetch 处理器
 *   换成 `e.respondWith(caches.match(e.request))`（缓存优先、永不回源、连 /api/ 都缓存、
 *   推送处理器整个删掉），把那些字样留在注释里 —— **三条同时绿**。
 *   而 sw.js 自己的注释里就写着：「静态测试只看『有 fetch 有 catch』，抓不到这个」。
 *   知道了，但没补。这份就是补上的那个。
 *
 * 它只用 node 内置的东西，不装任何包。node 不在就跳过（见 test_core 里的 skip）。
 * 输出一行 JSON 给 python 那头判。
 */
import fs from 'node:fs';
import vm from 'node:vm';

const swPath = process.argv[2];
const src = fs.readFileSync(swPath, 'utf8');

/* ── 最小的假 Response：body 只能读一次，谁重复 clone 谁当场炸 ─────────── */
class FakeResponse {
  constructor(body, { status = 200, url = '' } = {}) {
    this.status = status; this.url = url;
    this._body = body; this._used = false;
    this.type = 'basic';
  }
  get ok() { return this.status >= 200 && this.status < 300; }
  clone() {
    if (this._used) throw new TypeError("Failed to execute 'clone' on 'Response': Response body is already used");
    return new FakeResponse(this._body, { status: this.status, url: this.url });
  }
  consume() { this._used = true; return this._body; }   // 页面「读掉」body
}

/* ── 最小的假 CacheStorage ─────────────────────────────────────────── */
/* ★ 0902：sw.js 改成了相对路径（'./'、'./manifest.json'），好让它挂在子路径下也对。
   真浏览器会把相对 URL 按 SW 的 scope 解析成绝对的；这个台架原来只认字面串，
   `c.add('./')` 存进去的键是 './'，跟 routes['/'] / match('/') 对不上 —— 那是台架的模型缺了一块，
   不是 sw.js 错了。这里补上：scope 在台架里就是根 '/'，相对 → 绝对。 */
const SCOPE = '/';
const resolve = (u) => {
  if (u == null) return u;
  const s = String(u);
  if (/^https?:\/\//.test(s)) return s.replace(/^https?:\/\/[^/]+/, '');   // 'http://x/foo' → '/foo'
  if (s.startsWith('/')) return s;
  return SCOPE + s.replace(/^\.\//, '');                                     // './x' | 'x' | './' → '/x' | '/'
};
const keyOf = (req) => resolve(req && req.url != null ? req.url : req);

class FakeCache {
  constructor() { this.map = new Map(); }
  async put(req, res) {
    if (res && res._used) throw new TypeError('put 收到的是已经被读掉的 body');
    this.map.set(keyOf(req), res); return undefined;
  }
  async add(u) {
    const res = await env.fetch(new FakeRequest(resolve(u)));
    if (!res.ok) throw new TypeError('Request failed: ' + u);   // 规范：add 对非 2xx 直接 reject
    return this.put(u, res);
  }
  async match(req) { return this.map.get(keyOf(req)); }
}
class FakeCacheStorage {
  constructor() { this.stores = new Map(); }
  async open(v) { if (!this.stores.has(v)) this.stores.set(v, new FakeCache()); return this.stores.get(v); }
  async keys() { return [...this.stores.keys()]; }
  async delete(v) { return this.stores.delete(v); }
  async match(req) {
    for (const c of this.stores.values()) { const h = await c.match(req); if (h) return h; }
    return undefined;
  }
}

class FakeRequest {
  constructor(url, { mode = 'no-cors', method = 'GET', destination = '' } = {}) {
    this.url = 'http://x' + url; this.mode = mode; this.method = method; this.destination = destination;
  }
}

/* ── 环境 ──────────────────────────────────────────────────────────── */
const env = {
  listeners: {},
  fetchLog: [],
  netUp: true,
  routes: {},                       // path → status
  async fetch(req) {
    const path = String(req.url || req).replace('http://x', '');
    env.fetchLog.push(path);
    if (!env.netUp) throw new TypeError('Failed to fetch');
    const status = env.routes[path] ?? 200;
    return new FakeResponse('BODY ' + path, { status, url: 'http://x' + path });
  },
};

const sandbox = {
  self: {
    addEventListener: (t, fn) => { (env.listeners[t] ||= []).push(fn); },
    skipWaiting: async () => { env.skipWaiting = true; },
    clients: { claim: async () => {} },
    registration: { showNotification: async (t, o) => { env.notified = { t, o }; } },
  },
  caches: new FakeCacheStorage(),
  fetch: env.fetch,
  location: { origin: 'http://x' },
  URL, Promise, TypeError, console, clients: { matchAll: async () => [], openWindow: async () => {} },
};
sandbox.self.location = sandbox.location;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'sw.js' });

/* ── 驱动 ──────────────────────────────────────────────────────────── */
const fire = async (type, ev) => {
  for (const fn of env.listeners[type] || []) await fn(ev);
};
/* ★ 每条检查单独兜住：SW 坏成什么样都该给出干净的 false，
   不该抛一个栈出来 —— 崩溃的测试比红的测试难查。 */
const check = async (name, fn) => { try { out[name] = !!(await fn()); } catch (e) { out[name] = false; } };
const mkFetchEvent = (req) => {
  const ev = { request: req, _responded: false, _promise: null };
  ev.respondWith = (p) => { ev._responded = true; ev._promise = p; };
  return ev;
};
const install = async () => {
  const ev = { _p: null, waitUntil: (p) => { ev._p = p; } };
  await fire('install', ev);
  return ev._p;
};
const activate = async () => {
  const ev = { _p: null, waitUntil: (p) => { ev._p = p; } };
  await fire('activate', ev);
  return ev._p;
};

const out = {};
const V = () => [...sandbox.caches.stores.keys()][0];

/* ① 装一次，离线壳要在 */
await check('installedShell', async () => { await install(); return (await (await sandbox.caches.open(V() || 'x')).match('/')); });

/* ② 关键那条：`/` 拿不到时 install 必须**失败**，旧缓存才保得住 */
{
  const s2 = new FakeCacheStorage();
  const good = new FakeCache(); good.map.set('/', new FakeResponse('OLD SHELL'));
  s2.stores.set('lianhuan-OLD', good);
  sandbox.caches = s2;
  env.routes['/'] = 503;                       // 换版本那一刻网络抖了一下
  let failed = false;
  try { await install(); } catch (_) { failed = true; }
  out.installFailsWhenShellIsUnreachable = failed;
  // ★ 照真实生命周期来：install 失败 → 这一版根本不会 activate → 旧缓存原样保住。
  //   （台架第一版在这儿无条件跑了 activate，把旧壳自己删了，报了个假红。）
  if (!failed) await activate().catch(() => {});
  out.oldShellSurvives = !!(await s2.match('/'));
  delete env.routes['/'];
  sandbox.caches = new FakeCacheStorage();
  try { await install(); } catch (_) {}
}

/* ③ /api/ 一律不碰 —— 缓存过的对话是最坏的一种错误 */
{
  const ev = mkFetchEvent(new FakeRequest('/api/turns'));
  await fire('fetch', ev);
  out.apiUntouched = !ev._responded;
}
{
  const ev = mkFetchEvent(new FakeRequest('/chat'));
  await fire('fetch', ev);
  out.chatUntouched = !ev._responded;
}

/* ④ 页面导航 = 网络优先（改了代码打开就该是新的） */
{
  env.fetchLog = [];
  const ev = mkFetchEvent(new FakeRequest('/', { mode: 'navigate', destination: 'document' }));
  await fire('fetch', ev);
  await check('navigateHitsNetwork', async () => { await ev._promise; return env.fetchLog.includes('/'); });
}

/* ⑤ 静态资源 = 缓存优先 */
{
  const c = await sandbox.caches.open(V());
  await c.put('http://x/a.css', new FakeResponse('CACHED CSS'));
  env.fetchLog = [];
  const ev = mkFetchEvent(new FakeRequest('/a.css'));
  await fire('fetch', ev);
  await check('staticServedFromCache', async () => (await ev._promise)?._body === 'CACHED CSS');
}

/* ⑥ ★ 题目那条：非 200 的响应绝不许写进缓存 */
{
  env.routes['/boom'] = 404;
  const ev = mkFetchEvent(new FakeRequest('/boom', { mode: 'navigate', destination: 'document' }));
  await fire('fetch', ev);
  await check('errorPageNotCached', async () => {
    try { await ev._promise; } catch (_) {}
    const c = await sandbox.caches.open(V());
    return !(await c.match('http://x/boom'));
  });
  delete env.routes['/boom'];
}

/* ⑦ ★ clone 必须在 body 交给页面**之前**同步做完（GPT 四轮 P1-01 那个真 bug） */
{
  env.routes['/fresh.css'] = 200;
  const ev = mkFetchEvent(new FakeRequest('/fresh.css'));
  await fire('fetch', ev);
  await check('cacheUpdatedEvenAfterBodyConsumed', async () => {
    const res = await ev._promise;
    res.consume();                                // 页面立刻把 body 读掉
    await new Promise(r => setTimeout(r, 20));    // 让写缓存那条 promise 跑完
    const c = await sandbox.caches.open(V());
    return await c.match('http://x/fresh.css');
  });
}

/* ⑧ 断网时页面回落到离线壳 */
{
  env.netUp = false;
  const ev = mkFetchEvent(new FakeRequest('/anywhere', { mode: 'navigate', destination: 'document' }));
  await fire('fetch', ev);
  await check('offlineFallsBackToShell', async () => String((await ev._promise)?._body || '').includes('/'));
  env.netUp = true;
}

/* ⑨ 推送处理器真的注册了（不是注释里有那个字样） */
out.hasPush = (env.listeners.push || []).length > 0;
out.hasNotificationClick = (env.listeners.notificationclick || []).length > 0;
if (out.hasPush) {
  await check('pushTitleIsNeutral', async () => {
    await fire('push', { data: { json: () => ({ body: '在吗' }) }, waitUntil: (p) => p });
    return env.notified && env.notified.t && env.notified.t.length <= 4;
  });
}

console.log(JSON.stringify(out));
