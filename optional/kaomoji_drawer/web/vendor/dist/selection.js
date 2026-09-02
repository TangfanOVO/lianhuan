function recentPenalty(item, now) {
    const usedAt = item.lastUsedAt ? Date.parse(item.lastUsedAt) : Number.NaN;
    if (!Number.isFinite(usedAt))
        return 1;
    const age = Math.max(0, now - usedAt);
    if (age < 2 * 60_000)
        return 0.08;
    if (age < 60 * 60_000)
        return 0.35;
    if (age < 24 * 60 * 60_000)
        return 0.7;
    return 1;
}
export function selectDiverseKaomoji(ranked, recentValues = [], variety = "balanced", random = Math.random, now = Date.now()) {
    if (!ranked.length)
        return undefined;
    const poolSize = variety === "steady" ? 2 : variety === "fresh" ? 10 : 6;
    let pool = ranked.slice(0, poolSize);
    if (pool.length > 1) {
        const withoutLast = pool.filter((item) => item.value !== recentValues[0]);
        if (withoutLast.length)
            pool = withoutLast;
        const unseen = pool.filter((item) => !recentValues.includes(item.value));
        if (unseen.length >= 2 || unseen.length === pool.length)
            pool = unseen;
    }
    const weights = pool.map((item, index) => {
        const rankWeight = Math.max(1, pool.length - index);
        const preference = (item.favorite ? 1.2 : 1) * (1 + Math.min(0.45, Math.log1p(Math.max(0, item.useCount)) * 0.06));
        return rankWeight * preference * recentPenalty(item, now);
    });
    const total = weights.reduce((sum, weight) => sum + weight, 0);
    let target = random() * total;
    for (let index = 0; index < pool.length; index += 1) {
        target -= weights[index];
        if (target <= 0)
            return pool[index];
    }
    return pool.at(-1);
}
