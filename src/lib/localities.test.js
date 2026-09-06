// Grouping contract for the pan-India locality picker.
// Run with `bun test`.
//
// Break this test would catch: Mumbai neighbourhoods mixed into Maharashtra
// cities, Chennai filed under a Mumbai lat-band, or a missing state/metro
// silently dropping a row.

import { test, expect } from "bun:test";
import { groupOf, groupLocalities } from "./localities.js";
import { slugify } from "./slug.js";
import catalog from "../data/localities.json";


const colaba = { name: "Colaba", lat: 18.9151, lon: 72.8260, state: "Maharashtra", metro: "Mumbai" };
const pune = { name: "Pune", lat: 18.5204, lon: 73.8567, state: "Maharashtra" };
const chennai = { name: "Chennai", lat: 13.0827, lon: 80.2707, state: "Tamil Nadu" };
const ahmedabad = { name: "Ahmedabad", lat: 23.0225, lon: 72.5714, state: "Gujarat" };

test("groupOf uses metro when present, else state", () => {
  expect(groupOf(colaba)).toBe("Mumbai");
  expect(groupOf(pune)).toBe("Maharashtra");
  expect(groupOf(chennai)).toBe("Tamil Nadu");
});

test("groupOf sends untagged rows to More areas instead of dropping them", () => {
  expect(groupOf({ name: "Somewhere", lat: 0, lon: 0 })).toBe("More areas");
});

test("groupLocalities pins Mumbai first, then other groups A–Z", () => {
  const list = [ahmedabad, chennai, colaba, pune];
  const groups = groupLocalities(list);
  expect(groups.map((g) => g.title)).toEqual(["Mumbai", "Gujarat", "Maharashtra", "Tamil Nadu"]);
});

test("Pune is not in the Mumbai group", () => {
  const list = [colaba, pune];
  const groups = groupLocalities(list);
  const mumbai = groups.find((g) => g.title === "Mumbai");
  const mh = groups.find((g) => g.title === "Maharashtra");
  expect(mumbai.items.map((i) => list[i].name)).toEqual(["Colaba"]);
  expect(mh.items.map((i) => list[i].name)).toEqual(["Pune"]);
});

test("items inside a group are sorted by name", () => {
  const bandra = { name: "Bandra West", lat: 19.06, lon: 72.83, state: "Maharashtra", metro: "Mumbai" };
  const list = [colaba, bandra];
  const groups = groupLocalities(list);
  expect(groups[0].items.map((i) => list[i].name)).toEqual(["Bandra West", "Colaba"]);
});

test("empty list yields no groups", () => {
  expect(groupLocalities([])).toEqual([]);
});

test("every catalog row has a state so the picker can group", () => {
  for (const l of catalog) {
    expect(typeof l.state).toBe("string");
    expect(l.state.length).toBeGreaterThan(0);
  }
});

test("Colaba stays a Mumbai neighbourhood, not a Maharashtra city", () => {
  const col = catalog.find((l) => l.name === "Colaba");
  expect(col.metro).toBe("Mumbai");
  expect(col.state).toBe("Maharashtra");
});

test("major Indian cities are in the catalog", () => {
  const names = new Set(catalog.map((l) => l.name));
  for (const n of [
    "Chennai", "Bengaluru", "Delhi", "Kolkata", "Hyderabad",
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Guwahati",
    "Chandigarh", "Bhopal", "Patna", "Thiruvananthapuram", "Srinagar",
  ]) {
    expect(names.has(n)).toBe(true);
  }
});

test("catalog slugs are unique so SEO pages do not collide", () => {
  const slugs = catalog.map((l) => slugify(l.name));
  expect(new Set(slugs).size).toBe(slugs.length);
});

test("live catalog still pins Mumbai first", () => {
  expect(groupLocalities(catalog)[0].title).toBe("Mumbai");
});
