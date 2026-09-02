import { defaultKaomojiEntries } from "./default-library.js";
const transportControls = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g;
const riskyScripts = /[\u0980-\u0dff\u0f00-\u0fff\u1000-\u109f\u1780-\u17ff]/u;
const invalid = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffd]/u;
const categoryAliases = {
    cute: "可爱", affectionate: "亲亲", kiss: "亲亲", kissing: "亲亲",
    shy: "害羞", studying: "学习", study: "学习", sad: "伤心",
    cry: "哭哭", crying: "哭哭", angry: "生气", happy: "开心",
    cat: "猫猫", cats: "猫猫", rabbit: "兔兔", bunny: "兔兔",
    sheep: "羊羊", dog: "狗狗", dogs: "狗狗", sleepy: "困困",
    tired: "累", hug: "抱抱", surprised: "惊讶", surprise: "惊讶",
    confused: "迷惑", embarrassed: "尴尬", ugly: "丑陋", bad: "坏",
    serious: "严肃", tsundere: "傲娇", eating: "吃吃", food: "吃吃",
    love: "爱心", heart: "爱心", couple: "双人", duo: "双人",
    lost: "失落", helpless: "无奈", facepalm: "捂脸",
    ascii: "字符画", "ascii art": "字符画", ascii_art: "字符画", "character art": "字符画",
};
const categoryPriority = [
    "可爱", "开心", "亲亲", "害羞", "哭哭", "伤心", "生气", "猫猫", "狗狗", "兔兔",
    "困困", "吃吃", "爱心", "抱抱", "惊讶", "无奈", "尴尬", "迷惑", "傲娇", "双人",
    "震惊", "捂脸", "严肃", "失落", "坏", "丑陋",
];
export function normalizeKaomojiCategory(category) {
    const clean = category.trim().slice(0, 50);
    return categoryAliases[clean.toLocaleLowerCase()] ?? clean;
}
export function normalizeKaomojiCategories(categories) {
    return [...new Set(categories.map(normalizeKaomojiCategory).filter(Boolean))].slice(0, 8);
}
export function normalizeKaomojiCategoryOrder(categories) {
    return [...new Set(categories.map(normalizeKaomojiCategory).filter(Boolean))].slice(0, 100);
}
export function rankKaomojiCategories(items, manualOrder = []) {
    const statistics = new Map();
    for (const item of items) {
        for (const category of normalizeKaomojiCategories(item.categories)) {
            const current = statistics.get(category) ?? { uses: 0, favorites: 0, items: 0 };
            current.uses += Math.max(0, item.useCount || 0);
            current.favorites += Number(Boolean(item.favorite));
            current.items += 1;
            statistics.set(category, current);
        }
    }
    const automatic = [...statistics.keys()].sort((left, right) => {
        const a = statistics.get(left);
        const b = statistics.get(right);
        return b.uses - a.uses
            || b.favorites - a.favorites
            || (categoryPriority.indexOf(left) < 0 ? 999 : categoryPriority.indexOf(left))
                - (categoryPriority.indexOf(right) < 0 ? 999 : categoryPriority.indexOf(right))
            || b.items - a.items
            || left.localeCompare(right, "zh-CN");
    });
    if (!manualOrder.length)
        return automatic;
    const present = new Set(automatic);
    const manual = normalizeKaomojiCategoryOrder(manualOrder).filter((category) => present.has(category));
    return [...manual, ...automatic.filter((category) => !manual.includes(category))];
}
export function normalizeKaomoji(value) {
    return value.replace(transportControls, "").normalize("NFC").trim();
}
export function analyzeKaomoji(value, categories = []) {
    const clean = normalizeKaomoji(value);
    const notes = [];
    const asciiArt = normalizeKaomojiCategories(categories).includes("字符画");
    const invalidForKind = asciiArt
        ? /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffd]/u
        : invalid;
    if (invalidForKind.test(clean))
        notes.push("含有无法稳定传输的字符");
    if (/\p{Mark}{3,}/u.test(clean.normalize("NFD")))
        notes.push("叠加符号较多，部分设备会显示成黑条");
    if (riskyScripts.test(clean))
        notes.push("使用罕见字形，缺少字体时可能变成方块");
    const safe = clean.normalize("NFD").replace(/\p{Mark}/gu, "").replace(transportControls, "").replace(riskyScripts, "").normalize("NFC").trim();
    return {
        value: clean,
        compatibility: invalidForKind.test(clean) ? "blocked" : notes.length ? "limited" : "stable",
        compatibilityNotes: notes,
        safeValue: safe && safe !== clean ? safe : undefined,
    };
}
export function defaultKaomojiItems() {
    return defaultKaomojiEntries.map((entry) => ({
        ...analyzeKaomoji(entry.value, [...entry.categories]),
        categories: normalizeKaomojiCategories([...entry.categories]),
        favorite: false,
        useCount: 0,
    }));
}
export function decodeKaomojiState(value) {
    if (Array.isArray(value))
        return { version: 4, items: value, removed: [], categoryOrder: [] };
    if (value && typeof value === "object" && Array.isArray(value.items)) {
        const state = value;
        return {
            version: 4,
            items: state.items,
            removed: Array.isArray(state.removed) ? state.removed : [],
            categoryOrder: Array.isArray(state.categoryOrder) ? normalizeKaomojiCategoryOrder(state.categoryOrder) : [],
        };
    }
    return { version: 4, items: [], removed: [], categoryOrder: [] };
}
export function hydrateKaomojiState(state) {
    const removed = new Set(state.removed.map(normalizeKaomoji));
    const existing = new Map(state.items.map((item) => [normalizeKaomoji(item.value), item]));
    const items = defaultKaomojiItems()
        .filter((item) => !removed.has(item.value))
        .map((item) => existing.get(item.value) ?? item)
        .map((item) => ({ ...item, categories: normalizeKaomojiCategories(item.categories) }));
    const present = new Set(items.map((item) => item.value));
    for (const item of state.items) {
        const clean = normalizeKaomoji(item.value);
        if (!removed.has(clean) && !present.has(clean)) {
            items.push({ ...item, value: clean, categories: normalizeKaomojiCategories(item.categories) });
            present.add(clean);
        }
    }
    return { version: 4, items, removed: [...removed], categoryOrder: normalizeKaomojiCategoryOrder(state.categoryOrder) };
}
export function createLocalKaomojiRepository(storageKey = "fuyue.kaomoji.v1") {
    const readState = () => {
        const raw = window.localStorage.getItem(storageKey);
        if (raw) {
            try {
                return hydrateKaomojiState(decodeKaomojiState(JSON.parse(raw)));
            }
            catch { /* use defaults */ }
        }
        return hydrateKaomojiState(decodeKaomojiState(null));
    };
    const write = (state) => window.localStorage.setItem(storageKey, JSON.stringify(state));
    return {
        async list() {
            return readState().items.sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.compatibility.localeCompare(b.compatibility) || b.useCount - a.useCount);
        },
        async upsert(value, categories, label) {
            const cleanCategories = normalizeKaomojiCategories(categories);
            const analysis = analyzeKaomoji(value, cleanCategories);
            const state = readState();
            const previous = state.items.find((item) => item.value === analysis.value);
            const saved = {
                ...analysis,
                label: label?.trim() || previous?.label,
                categories: cleanCategories,
                favorite: previous?.favorite ?? false,
                useCount: previous?.useCount ?? 0,
                lastUsedAt: previous?.lastUsedAt,
            };
            write({ ...state, items: [saved, ...state.items.filter((item) => item.value !== saved.value)], removed: state.removed.filter((item) => item !== saved.value) });
            return saved;
        },
        async remove(value) {
            const state = readState();
            const clean = normalizeKaomoji(value);
            write({ ...state, items: state.items.filter((item) => item.value !== clean), removed: [...new Set([...state.removed, clean])] });
        },
        async markUsed(value) {
            const state = readState();
            write({ ...state, items: state.items.map((item) => item.value === value ? { ...item, useCount: item.useCount + 1, lastUsedAt: new Date().toISOString() } : item) });
        },
        async setFavorite(value, favorite) {
            const state = readState();
            write({ ...state, items: state.items.map((item) => item.value === value ? { ...item, favorite } : item) });
        },
        async getCategoryOrder() {
            return readState().categoryOrder;
        },
        async setCategoryOrder(categories) {
            const state = readState();
            write({ ...state, categoryOrder: normalizeKaomojiCategoryOrder(categories) });
        },
        async mergeCatalog(entries) {
            const state = readState();
            const removed = new Set(state.removed.map(normalizeKaomoji));
            const existing = new Set(state.items.map((item) => normalizeKaomoji(item.value)));
            const additions = [];
            for (const entry of entries) {
                const value = normalizeKaomoji(entry.value);
                if (!value || removed.has(value) || existing.has(value))
                    continue;
                const categories = normalizeKaomojiCategories(entry.categories);
                additions.push({
                    ...analyzeKaomoji(value, categories),
                    label: entry.label?.trim() || undefined,
                    categories,
                    favorite: false,
                    useCount: 0,
                });
                existing.add(value);
            }
            if (additions.length)
                write({ ...state, items: [...additions, ...state.items] });
            return { added: additions.length, skipped: entries.length - additions.length };
        },
    };
}
