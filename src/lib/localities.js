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

// City-first picker: metros (Mumbai) collapse to one city with child neighbourhood
// indices; every other row is a city with no children.
export function cityCatalog(list) {
  const metros = new Map();
  const cities = [];
  (list || []).forEach((l, i) => {
    if (l && l.metro) {
      let m = metros.get(l.metro);
      if (!m) {
        m = { name: l.metro, state: l.state || "", lat: l.lat, lon: l.lon, children: [] };
        metros.set(l.metro, m);
      }
      m.children.push(i);
    } else if (l) {
      cities.push({
        name: l.name, state: l.state || "", lat: l.lat, lon: l.lon, index: i, children: [],
      });
    }
  });
  for (const m of metros.values()) {
    let slat = 0, slon = 0;
    m.children.forEach((i) => { slat += list[i].lat; slon += list[i].lon; });
    const n = m.children.length || 1;
    m.lat = slat / n;
    m.lon = slon / n;
  }
  return { metros: [...metros.values()], cities };
}

export function groupCities(list) {
  const { metros, cities } = cityCatalog(list);
  const groups = [];
  const mumbai = metros.filter((m) => m.name === "Mumbai");
  const otherMetros = metros.filter((m) => m.name !== "Mumbai");
  if (mumbai.length) groups.push({ title: "Mumbai", items: mumbai });
  const byState = new Map();
  for (const c of [...otherMetros, ...cities]) {
    const s = c.state || "More areas";
    if (!byState.has(s)) byState.set(s, []);
    byState.get(s).push(c);
  }
  [...byState.keys()].sort((a, b) => a.localeCompare(b)).forEach((s) => {
    const items = byState.get(s).sort((a, b) => a.name.localeCompare(b.name));
    groups.push({ title: s, items });
  });
  return groups;
}
