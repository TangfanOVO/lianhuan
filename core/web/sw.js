/* Service Worker —— 只做一件事：**壳先出来，别对着白屏等网**。
 *
 * 策略是「壳缓存，数据不缓存」：
 *   · **页面本身 → 网络优先**，断网才回缓存（0831 改的：原来页面也吃
 *     stale-while-revalidate，改完代码第一次打开必定是旧版，最难查）
 *   · 样式/脚本/图标 → 缓存优先，后台再更新（stale-while-revalidate；它们的 URL 带内容指纹）
 *   · /api/ 和 /chat  → **一律不缓存**。缓存过的对话和记忆是最坏的一种错误 ——
 *     它会让人看着旧数据以为是新的。宁可显示「连不上」。
 *
 * ★ 换版本号就会清掉旧缓存。改了壳记得改这里，不然人会拿到旧的。
 */
const V = 'lianhuan-v5';
/* ★ 0831 自查（病灶 12 顺手挖到的）：这里原来是一份 SHELL 数组 + `allSettled`，
 *   理由写着「addAll 一个失败会整批失败 —— 逐个来，少一个不至于让整个 SW 装不上」。
 *   理由本身是对的，但它把 `/` 和图标一视同仁了 —— 而 `/` 不是「少一个」，它**就是**离线壳。
 *   于是有一条真路径能把离线壳整个弄没：换了版本号之后，那一次 install 碰上网络抖动，
 *   `c.add('/')` 失败被 allSettled 咽掉 → 照样 skipWaiting → activate 无条件删掉所有旧缓存
 *   → 新缓存是空的、旧缓存没了 → 下面第 53 行的回落链 `hit || caches.match('/')` 解析成
 *   undefined，`respondWith(undefined)` 直接变网络错误 —— **离线打开就是浏览器错误页**。
 *   （症状跟题目问的那个「404 写进离线壳」一模一样，病根不同。）
 *   分成两档：`/` 装不上就让这次 install 整个失败（SW 留在老版本、旧缓存原样保住），
 *   其余的照旧「少一个不至于装不上」。 */
const SHELL_MUST = './';                                 // 离线壳本体（相对：挂在子路径下也对）
/* ★ 0902：原来这里还列着 /blocks/base/tokens.css 和 accent.js —— core/web 下根本没有这两个文件，
     index.html 也一次没引，是两条永远 404 的死条目（allSettled 咽掉了所以没人发现）。去掉。 */
const SHELL_NICE = ['./manifest.json', './icons/icon.svg', './icons/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(V)
    .then(c => c.add(SHELL_MUST)                          // 这个失败 → 整个 install 失败
                .then(() => Promise.allSettled(SHELL_NICE.map(u => c.add(u)))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  // ★ 数据永远走网络。缓存过的对话比看不到对话更糟
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/chat')) return;

  /* ★ 0831：**页面本身走网络优先**，断网才回缓存。
     原来页面也吃 stale-while-revalidate —— 改了代码之后第一次打开必定是旧版
     （真机上当场撞见：删掉的演示气泡又出现了一次）。
     这是自托管场景，更新完看到旧页面等于「改了没生效」，最难查。
     其余静态资源（css/js/图标）照旧缓存优先，它们的 URL 带内容指纹。 */
  /* ★ 0831（GPT 四轮 P1-01）：clone 必须在 response 交出去**之前**同步做完。
     原来写成 `caches.open(V).then(c => c.put(req, res.clone()))` —— 等那个 promise
     回来时 body 早被页面消费了，真机上连续抛
     `Failed to execute 'clone' on 'Response': Response body is already used`，
     缓存其实一次都没更新成功（静态测试只看「有 fetch 有 catch」，抓不到这个）。 */
  const stash = (req, res) => {
    if (!res || !res.ok) return res;
    const copy = res.clone();                      // ← 同步克隆，就在这一刻
    caches.open(V).then(c => c.put(req, copy)).catch(() => {});
    return res;
  };

  if (e.request.mode === 'navigate' || e.request.destination === 'document'){
    e.respondWith(
      fetch(e.request).then(res => stash(e.request, res))
        .catch(() => caches.match(e.request).then(hit => hit || caches.match('./')))
    );
    return;
  }

  e.respondWith(caches.match(e.request).then(hit => {
    const net = fetch(e.request).then(res => stash(e.request, res))
                                .catch(() => hit);   // 断网就用缓存；缓存也没有就让它自然失败
    return hit || net;
  }));
});

/* ══ Web Push（照原项目 sw 的两段平移）══
 * payload 由后端给：{title, body, url}。title 是设置里给他起的名字。 */
self.addEventListener('push', event => {
  let d = { title: '他', body: '', url: '/' };
  try { d = Object.assign(d, event.data.json()); } catch (_) {}
  event.waitUntil(
    self.registration.showNotification(d.title || '他', {
      body: d.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: 'lianhuan',
      data: { url: d.url || '/' }
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
