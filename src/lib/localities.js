// Locality picker grouping. Mumbai neighbourhoods stay a pinned "Mumbai"
// group via `metro`; every other row groups by `state`. Untagged rows land
// in "More areas" so a data miss never drops a place from the picker.

const PINNED = ["Mumbai"];
const FALLBACK = "More areas";

export function groupOf(loc) {
  const metro = loc && typeof loc.metro === "string" ? loc.metro.trim() : "";
  if (metro) return metro;
  const state = loc && typeof loc.state === "string" ? loc.state.trim() : "";
  if (state) return state;
  return FALLBACK;
}

export function groupLocalities(list) {
  if (!list || !list.length) return [];
  const buckets = new Map();
  list.forEach((loc, i) => {
    const title = groupOf(loc);
    if (!buckets.has(title)) buckets.set(title, []);
    buckets.get(title).push(i);
  });
  const byName = (a, b) => list[a].name.localeCompare(list[b].name);
  const rest = [...buckets.keys()]
    .filter((t) => !PINNED.includes(t) && t !== FALLBACK)
    .sort((a, b) => a.localeCompare(b));
  const order = [
    ...PINNED.filter((t) => buckets.has(t)),
    ...rest,
    ...(buckets.has(FALLBACK) ? [FALLBACK] : []),
  ];
  return order.map((title) => ({ title, items: buckets.get(title).sort(byName) }));
}
