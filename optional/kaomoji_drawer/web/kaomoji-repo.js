/* 颜文字数据层 · 0826
 *
 * 实现 fuyue-kaomoji-drawer（MIT，见 UPSTREAM）的 KaomojiRepository 接口，后端走
 * /api/kaomoji/v2。网页上点的、AI 用 MCP 挑的，写的是同一份库。
 *
 * ★ DESIGN.md §5之二：fetch 只许出现在数据层。皮肤代码只管渲染，不许自己取数。
 *   这个文件就是那一层 —— 抽屉组件拿到的是接口，不是 URL。
 */
import { analyzeKaomoji, normalizeKaomoji } from "./vendor/dist/repository.js";

export function createRemoteKaomojiRepository(base = "/api/kaomoji/v2") {
  let cache = null;      // 整份 state，读一次就缓存
  let loading = null;    // 并发的首读合并成一个请求

  async function load() {
    if (cache) return cache;
    if (loading) return loading;
    loading = fetch(base)
      .then(r => { if (!r.ok) throw new Error("读不到颜文字库 " + r.status); return r.json(); })
      .then(st => {
        cache = {
          version: st.version || 4,
          items: Array.isArray(st.items) ? st.items : [],
          removed: Array.isArray(st.removed) ? st.removed : [],
          categoryOrder: Array.isArray(st.categoryOrder) ? st.categoryOrder : [],
        };
        return cache;
      })
      .finally(() => { loading = null; });
    return loading;
  }

  async function post(body) {
    const r = await fetch(base, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const out = await r.json().catch(() => ({}));
    if (!r.ok || out.err) throw new Error(out.err || ("存不上 " + r.status));
    return out;
  }

  const find = v => cache?.items.find(i => i.value === v);

  return {
    async list() {
      const st = await load();
      // ★ 必须给新对象。直接返回缓存里那个数组，React 见引用没变就不重渲染 ——
      //   收藏点下去后端存上了、星星却不亮，就是这么来的（0826 栽过一次）。
      return st.items.map(i => ({ ...i }));
    },

    async upsert(value, categories, label) {
      const v = normalizeKaomoji(value);
      const st = await load();
      const cats = (categories || []).filter(Boolean);
      // 兼容性在这边算 —— 后端没有他那套 Unicode 判定，别让它去猜
      const a = analyzeKaomoji(v, cats);
      const out = await post({
        op: "upsert", value: v, categories: cats, label,
        compatibility: a.compatibility,
        compatibilityNotes: a.compatibilityNotes,
        safeValue: a.safeValue,
      });
      const item = out.item;
      const prev = find(v);
      if (prev) Object.assign(prev, item);
      else st.items.push(item);
      st.removed = st.removed.filter(r => r !== v);
      return item;
    },

    async remove(value) {
      const st = await load();
      await post({ op: "remove", value });
      st.items = st.items.filter(i => i.value !== value);
      if (!st.removed.includes(value)) st.removed.push(value);
    },

    async markUsed(value) {
      const st = await load();
      const it = find(value);
      // 乐观更新：点一下就该立刻插进去，不等网络
      if (it) { it.useCount = (it.useCount || 0) + 1; it.lastUsedAt = new Date().toISOString(); }
      try {
        await post({ op: "markUsed", value });
      } catch (e) {
        if (it) it.useCount = Math.max(0, (it.useCount || 1) - 1);  // 没记上就退回去
        console.warn("[颜文字] 用量没记上:", e.message);
      }
      return st;
    },

    async setFavorite(value, favorite) {
      const it = find(value);
      const before = it?.favorite;
      if (it) it.favorite = favorite;
      try {
        await post({ op: "setFavorite", value, favorite });
      } catch (e) {
        if (it && before !== undefined) it.favorite = before;
        throw e;
      }
    },

    async getCategoryOrder() {
      const st = await load();
      return st.categoryOrder;
    },

    async setCategoryOrder(categories) {
      const st = await load();
      const before = st.categoryOrder;
      st.categoryOrder = categories;
      try {
        await post({ op: "setCategoryOrder", categories });
      } catch (e) {
        st.categoryOrder = before;
        throw e;
      }
    },
  };
}
