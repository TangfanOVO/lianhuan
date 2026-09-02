import { analyzeKaomoji, normalizeKaomoji, normalizeKaomojiCategories } from "./repository.js";
export const defaultKaomojiCatalogManifestUrl = "https://raw.githubusercontent.com/TangfanOVO/fuyue-kaomoji-drawer/main/catalog/manifest.json";
export const defaultKaomojiCatalogStateStorageKey = "fuyue.kaomoji.catalog.v1";
export const defaultKaomojiCatalogCheckIntervalMs = 24 * 60 * 60 * 1000;
function storage() {
    return typeof window === "undefined" ? undefined : window.localStorage;
}
export function readKaomojiCatalogSyncState(storageKey = defaultKaomojiCatalogStateStorageKey) {
    const fallback = { mode: "manual" };
    try {
        const raw = storage()?.getItem(storageKey);
        if (!raw)
            return fallback;
        const parsed = JSON.parse(raw);
        const mode = ["manual", "automatic", "off"].includes(String(parsed.mode))
            ? parsed.mode
            : "manual";
        return {
            mode,
            lastCheckedAt: typeof parsed.lastCheckedAt === "string" ? parsed.lastCheckedAt : undefined,
            lastSyncedAt: typeof parsed.lastSyncedAt === "string" ? parsed.lastSyncedAt : undefined,
            libraryVersion: typeof parsed.libraryVersion === "string" ? parsed.libraryVersion : undefined,
            lastAdded: Number.isFinite(parsed.lastAdded) ? Number(parsed.lastAdded) : undefined,
        };
    }
    catch {
        return fallback;
    }
}
export function writeKaomojiCatalogSyncState(state, storageKey = defaultKaomojiCatalogStateStorageKey) {
    storage()?.setItem(storageKey, JSON.stringify(state));
}
function validManifest(value) {
    if (!value || typeof value !== "object")
        return false;
    const manifest = value;
    return manifest.schemaVersion === 1
        && typeof manifest.libraryVersion === "string"
        && typeof manifest.generatedAt === "string"
        && Number.isInteger(manifest.itemCount)
        && Number(manifest.itemCount) >= 0
        && Number(manifest.itemCount) <= 10_000
        && typeof manifest.itemsUrl === "string";
}
function validEntries(value) {
    if (!Array.isArray(value) || value.length > 10_000)
        throw new Error("精选库数据格式不正确");
    const seen = new Set();
    const entries = [];
    for (const candidate of value) {
        if (!candidate || typeof candidate !== "object")
            continue;
        const raw = candidate;
        if (typeof raw.value !== "string" || !Array.isArray(raw.categories))
            continue;
        const value = normalizeKaomoji(raw.value);
        const categories = normalizeKaomojiCategories(raw.categories.filter((part) => typeof part === "string"));
        const analysis = analyzeKaomoji(value, categories);
        if (!value || value.length > 500 || !categories.length || analysis.compatibility === "blocked" || seen.has(value))
            continue;
        seen.add(value);
        entries.push({ value, categories, label: typeof raw.label === "string" ? raw.label.slice(0, 100) : undefined });
    }
    return entries;
}
async function fetchJson(fetcher, url, maxCharacters) {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:")
        throw new Error("精选库地址必须使用 HTTPS");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    try {
        const response = await fetcher(parsed.href, { headers: { Accept: "application/json" }, signal: controller.signal });
        if (!response.ok)
            throw new Error(`精选库连接失败（${response.status}）`);
        const text = await response.text();
        if (text.length > maxCharacters)
            throw new Error("精选库数据过大，已停止同步");
        return JSON.parse(text);
    }
    finally {
        clearTimeout(timeout);
    }
}
async function mergeFallback(repository, entries) {
    const existing = new Set((await repository.list()).map((item) => normalizeKaomoji(item.value)));
    let added = 0;
    for (const item of entries) {
        if (existing.has(item.value))
            continue;
        await repository.upsert(item.value, item.categories, item.label);
        existing.add(item.value);
        added += 1;
    }
    return { added, skipped: entries.length - added };
}
export async function syncKaomojiCatalog(repository, options = {}) {
    const fetcher = options.fetcher ?? globalThis.fetch;
    if (!fetcher)
        throw new Error("当前环境不支持联网同步");
    const manifestUrl = options.manifestUrl ?? defaultKaomojiCatalogManifestUrl;
    const manifestRaw = await fetchJson(fetcher, manifestUrl, 64_000);
    if (!validManifest(manifestRaw))
        throw new Error("精选库清单格式不正确");
    const itemsUrl = new URL(manifestRaw.itemsUrl, manifestUrl).href;
    const entries = validEntries(await fetchJson(fetcher, itemsUrl, 2_000_000));
    if (entries.length !== manifestRaw.itemCount)
        throw new Error("精选库条目数校验失败");
    const result = repository.mergeCatalog
        ? await repository.mergeCatalog(entries)
        : await mergeFallback(repository, entries);
    return { ...result, manifest: manifestRaw };
}
export function shouldAutomaticallySync(state, options = {}, now = Date.now()) {
    if (state.mode !== "automatic")
        return false;
    const lastChecked = state.lastCheckedAt ? Date.parse(state.lastCheckedAt) : 0;
    return !Number.isFinite(lastChecked) || now - lastChecked >= (options.checkIntervalMs ?? defaultKaomojiCatalogCheckIntervalMs);
}
