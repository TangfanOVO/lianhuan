import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useCallback, useEffect, useMemo, useState } from "react";
import { readKaomojiCatalogSyncState, shouldAutomaticallySync, syncKaomojiCatalog, writeKaomojiCatalogSyncState } from "./catalog-sync.js";
import { rankKaomojiCategories } from "./repository.js";
export function splitKaomojiCategories(value) {
    return [...new Set(value.split(/[,，、/]+/).map((part) => part.trim()).filter(Boolean))].slice(0, 8);
}
export function KaomojiDrawer({ repository, reviewRepository, onInsert, title = "颜文字库", catalog = {} }) {
    const [items, setItems] = useState([]);
    const [candidates, setCandidates] = useState([]);
    const [candidateCategories, setCandidateCategories] = useState({});
    const [query, setQuery] = useState("");
    const [category, setCategory] = useState("");
    const [managing, setManaging] = useState(false);
    const [manageView, setManageView] = useState("library");
    const [busyCandidate, setBusyCandidate] = useState(null);
    const [newValue, setNewValue] = useState("");
    const [newCategories, setNewCategories] = useState("可爱");
    const [categoryOrder, setCategoryOrder] = useState([]);
    const [draggedCategory, setDraggedCategory] = useState("");
    const catalogOptions = useMemo(() => catalog || {}, [catalog]);
    const catalogStorageKey = catalogOptions.stateStorageKey;
    const [catalogState, setCatalogState] = useState(() => readKaomojiCatalogSyncState(catalogStorageKey));
    const [catalogBusy, setCatalogBusy] = useState(false);
    const [catalogMessage, setCatalogMessage] = useState("");
    const [catalogError, setCatalogError] = useState("");
    const refresh = () => repository.list().then(setItems);
    const refreshCandidates = () => reviewRepository?.listCandidates().then((next) => {
        setCandidates(next);
        setCandidateCategories((current) => Object.fromEntries(next.map((candidate) => [String(candidate.id), current[String(candidate.id)] ?? candidate.suggestedCategories.join("，")])));
    });
    useEffect(() => {
        void refresh();
        void repository.getCategoryOrder?.().then(setCategoryOrder);
    }, [repository]);
    useEffect(() => { void refreshCandidates(); }, [reviewRepository]);
    const runCatalogSync = useCallback(async () => {
        if (catalog === false || catalogBusy)
            return;
        setCatalogBusy(true);
        setCatalogError("");
        setCatalogMessage("");
        const checkedAt = new Date().toISOString();
        try {
            const result = await syncKaomojiCatalog(repository, catalogOptions);
            const next = {
                ...catalogState,
                lastCheckedAt: checkedAt,
                lastSyncedAt: checkedAt,
                libraryVersion: result.manifest.libraryVersion,
                lastAdded: result.added,
            };
            setCatalogState(next);
            writeKaomojiCatalogSyncState(next, catalogStorageKey);
            setCatalogMessage(result.added ? `收进 ${result.added} 枚新颜文字` : "已经是最新的啦");
            await refresh();
        }
        catch (error) {
            const next = { ...catalogState, lastCheckedAt: checkedAt };
            setCatalogState(next);
            writeKaomojiCatalogSyncState(next, catalogStorageKey);
            setCatalogError(error instanceof Error ? error.message : "同步失败，请稍后再试");
        }
        finally {
            setCatalogBusy(false);
        }
    }, [catalog, catalogBusy, catalogOptions, catalogState, catalogStorageKey, repository]);
    useEffect(() => {
        if (catalog !== false && shouldAutomaticallySync(catalogState, catalogOptions))
            void runCatalogSync();
    }, [catalog, catalogOptions, catalogState, runCatalogSync]);
    const setCatalogMode = (mode) => {
        const next = { ...catalogState, mode };
        setCatalogState(next);
        writeKaomojiCatalogSyncState(next, catalogStorageKey);
        setCatalogMessage(mode === "automatic" ? "以后会静静检查新内容" : mode === "manual" ? "只在你点同步时更新" : "已关闭精选库同步");
        setCatalogError("");
    };
    const categories = useMemo(() => rankKaomojiCategories(items, categoryOrder), [categoryOrder, items]);
    const visible = items.filter((item) => (!category || item.categories.includes(category)) && (!query || [item.value, item.label || "", ...item.categories].some((part) => part.toLowerCase().includes(query.toLowerCase()))));
    const insert = async (item) => { onInsert(item.value); await repository.markUsed(item.value); void refresh(); };
    const save = async () => {
        if (!newValue.trim())
            return;
        await repository.upsert(newValue, splitKaomojiCategories(newCategories));
        setNewValue("");
        void refresh();
    };
    const saveCategoryOrder = async (next) => {
        setCategoryOrder(next);
        await repository.setCategoryOrder?.(next);
    };
    const moveCategory = (value, offset) => {
        const from = categories.indexOf(value);
        const to = from + offset;
        if (from < 0 || to < 0 || to >= categories.length)
            return;
        const next = [...categories];
        [next[from], next[to]] = [next[to], next[from]];
        void saveCategoryOrder(next);
    };
    const dropCategory = (target) => {
        const from = categories.indexOf(draggedCategory);
        const to = categories.indexOf(target);
        setDraggedCategory("");
        if (from < 0 || to < 0 || from === to)
            return;
        const next = [...categories];
        const [moved] = next.splice(from, 1);
        next.splice(to, 0, moved);
        void saveCategoryOrder(next);
    };
    const review = async (candidate, decision, acceptedVersion = "original") => {
        if (!reviewRepository)
            return;
        const key = String(candidate.id);
        setBusyCandidate(key);
        try {
            await reviewRepository.reviewCandidate(candidate.id, decision, {
                acceptedVersion,
                categories: splitKaomojiCategories(candidateCategories[key] || candidate.suggestedCategories.join("，")),
            });
            await Promise.all([refresh(), refreshCandidates()]);
        }
        finally {
            setBusyCandidate(null);
        }
    };
    return _jsxs("section", { className: "fy-kaomoji", "aria-label": title, children: [_jsxs("header", { children: [_jsxs("span", { children: [_jsx("b", { children: title }), _jsx("small", { children: "\u5DF2\u5E26\u5BA1\u6838\u597D\u7684\u9ED8\u8BA4\u5E93\uFF0C\u4F7F\u7528\u9891\u7387\u53EA\u5728\u672C\u5730\u6392\u5E8F" })] }), _jsx("button", { onClick: () => setManaging((value) => !value), children: managing ? "完成" : "整理" })] }), managing && reviewRepository && _jsxs("div", { className: "fy-kaomoji-segments", role: "tablist", "aria-label": "\u6574\u7406\u989C\u6587\u5B57", children: [_jsx("button", { className: manageView === "library" ? "current" : "", onClick: () => setManageView("library"), role: "tab", children: "\u6211\u7684\u5E93" }), _jsxs("button", { className: manageView === "review" ? "current" : "", onClick: () => setManageView("review"), role: "tab", children: ["\u5019\u9009\u7BB1", candidates.length ? ` ${candidates.length}` : ""] })] }), managing && manageView === "library" && _jsxs(_Fragment, { children: [_jsxs("div", { className: "fy-kaomoji-add", children: [_jsx("input", { value: newValue, onChange: (event) => setNewValue(event.target.value), placeholder: "\u7C98\u8D34\u4E00\u679A\u989C\u6587\u5B57" }), _jsx("input", { value: newCategories, onChange: (event) => setNewCategories(event.target.value), placeholder: "\u5206\u7C7B\uFF0C\u53EF\u586B\u591A\u4E2A" }), _jsx("button", { onClick: () => void save(), children: "\u6536\u8FDB\u6765" })] }), catalog !== false && _jsxs("section", { className: "fy-kaomoji-sync", "aria-label": "\u7CBE\u9009\u5E93\u540C\u6B65", children: [_jsxs("div", { children: [_jsx("b", { children: "\u7CBE\u9009\u5E93" }), _jsx("small", { children: catalogState.libraryVersion ? `当前 ${catalogState.libraryVersion}` : "审核过的新内容，不重装也能收进来" })] }), _jsxs("div", { className: "fy-kaomoji-sync-modes", role: "group", "aria-label": "\u540C\u6B65\u65B9\u5F0F", children: [_jsx("button", { className: catalogState.mode === "automatic" ? "current" : "", onClick: () => setCatalogMode("automatic"), children: "\u81EA\u52A8\u540C\u6B65" }), _jsx("button", { className: catalogState.mode === "manual" ? "current" : "", onClick: () => setCatalogMode("manual"), children: "\u4EC5\u624B\u52A8" }), _jsx("button", { className: catalogState.mode === "off" ? "current" : "", onClick: () => setCatalogMode("off"), children: "\u5173\u95ED" })] }), _jsx("button", { className: "fy-kaomoji-sync-now", disabled: catalogBusy || catalogState.mode === "off", onClick: () => void runCatalogSync(), children: catalogBusy ? "正在同步…" : "立即同步" }), (catalogMessage || catalogError) && _jsx("p", { className: catalogError ? "error" : "", role: catalogError ? "alert" : "status", children: catalogError || catalogMessage })] }), repository.setCategoryOrder && _jsxs("details", { className: "fy-kaomoji-order", children: [_jsxs("summary", { children: [_jsxs("span", { children: [_jsx("b", { children: "\u5206\u7C7B\u987A\u5E8F" }), _jsx("small", { children: "\u62D6\u52A8\uFF0C\u6216\u7528\u7BAD\u5934\u624B\u52A8\u6392" })] }), _jsx("i", { children: "\u2314" })] }), _jsx("div", { children: categories.map((value, index) => _jsxs("p", { className: draggedCategory === value ? "dragging" : "", draggable: true, onDragStart: () => setDraggedCategory(value), onDragEnd: () => setDraggedCategory(""), onDragOver: (event) => event.preventDefault(), onDrop: () => dropCategory(value), children: [_jsx("i", { children: "\u2807" }), _jsx("span", { children: value }), _jsx("button", { disabled: index === 0, onClick: () => moveCategory(value, -1), "aria-label": `上移${value}`, children: "\u2191" }), _jsx("button", { disabled: index === categories.length - 1, onClick: () => moveCategory(value, 1), "aria-label": `下移${value}`, children: "\u2193" })] }, value)) }), _jsx("button", { className: "fy-kaomoji-order-reset", disabled: !categoryOrder.length, onClick: () => void saveCategoryOrder([]), children: "\u6062\u590D\u667A\u80FD\u987A\u5E8F" })] })] }), managing && manageView === "review" && reviewRepository ? _jsx("div", { className: "fy-kaomoji-review", children: candidates.length ? candidates.map((candidate) => {
                    const key = String(candidate.id);
                    const busy = busyCandidate === key;
                    return _jsxs("article", { className: "fy-kaomoji-candidate", children: [_jsx("strong", { children: candidate.value }), candidate.compatibility !== "stable" && _jsx("small", { children: candidate.compatibilityNotes.join("；") || "跨设备可能易乱码" }), candidate.safeValue && _jsxs("div", { children: [_jsx("span", { children: "\u517C\u5BB9\u7248" }), _jsx("b", { children: candidate.safeValue })] }), _jsxs("label", { children: [_jsx("span", { children: "\u5206\u7C7B\uFF08\u53EF\u591A\u4E2A\uFF09" }), _jsx("input", { value: candidateCategories[key] ?? candidate.suggestedCategories.join("，"), onChange: (event) => setCandidateCategories((current) => ({ ...current, [key]: event.target.value })) })] }), _jsxs("footer", { className: candidate.safeValue ? "has-compatible" : "", children: [_jsx("button", { disabled: busy, onClick: () => void review(candidate, "rejected"), children: "\u4E0D\u6536" }), _jsx("button", { disabled: busy, onClick: () => void review(candidate, "approved", "original"), children: "\u6536\u539F\u7248" }), candidate.safeValue && _jsx("button", { disabled: busy, onClick: () => void review(candidate, "approved", "compatible"), children: "\u6536\u517C\u5BB9\u7248" })] })] }, key);
                }) : _jsx("div", { className: "fy-kaomoji-empty", children: "\u5019\u9009\u7BB1\u5DF2\u7ECF\u7406\u5B8C\u5566" }) }) : _jsxs(_Fragment, { children: [_jsx("input", { className: "fy-kaomoji-search", value: query, onChange: (event) => setQuery(event.target.value), placeholder: "\u641C\u7D22\u5FC3\u60C5\u3001\u5F62\u72B6\u6216\u5206\u7C7B" }), _jsxs("nav", { children: [_jsx("button", { className: !category ? "current" : "", onClick: () => setCategory(""), children: "\u5168\u90E8" }), categories.map((value) => _jsx("button", { className: category === value ? "current" : "", onClick: () => setCategory(value), children: value }, value))] }), _jsx("div", { className: "fy-kaomoji-grid", children: visible.map((item) => _jsxs("article", { className: item.categories.includes("字符画") ? "ascii-art" : "", children: [_jsx("button", { className: "fy-kaomoji-value", onClick: () => void insert(item), title: item.compatibilityNotes.join("；"), children: item.value }), item.compatibility !== "stable" && _jsx("span", { children: "\u6613\u4E71\u7801" }), managing ? _jsx("button", { className: "fy-kaomoji-remove", onClick: async () => { await repository.remove(item.value); void refresh(); }, "aria-label": "\u5220\u9664", children: "\u00D7" }) : _jsx("button", { className: "fy-kaomoji-star", onClick: async () => { await repository.setFavorite(item.value, !item.favorite); void refresh(); }, "aria-label": "\u6536\u85CF", children: item.favorite ? "★" : "☆" })] }, item.value)) })] })] });
}
