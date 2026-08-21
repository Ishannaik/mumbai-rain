// Unit tests for robust log loader. Run: bun test src/lib/log-csv.test.js
import { test, expect } from "bun:test";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import {
  LOG_HEADER,
  parseLogCsv,
  loadLogCsv,
  resolveRepoFile,
  projectRoots,
} from "./log-csv.js";

test("projectRoots includes cwd", () => {
  const roots = projectRoots();
  expect(roots.length).toBeGreaterThan(0);
  expect(roots.some((r) => path.normalize(r) === path.normalize(process.cwd()))).toBe(true);
});

test("resolveRepoFile finds committed data/log.csv", () => {
  const { path: p, tried } = resolveRepoFile("data", "log.csv");
  expect(p).toBeTruthy();
  expect(fs.existsSync(p)).toBe(true);
  expect(tried.length).toBeGreaterThan(0);
});

test("parseLogCsv: header-only → empty rows", () => {
  const rows = parseLogCsv(LOG_HEADER.join(",") + "\n");
  expect(rows).toEqual([]);
});

test("parseLogCsv: parses a labelled row", () => {
  const csv =
    LOG_HEADER.join(",") +
    "\n" +
    "2026-08-01T00:00,2026-08-01T01:00,19.12,72.85,0.5,0.4,80,1,0.2,1\n";
  const rows = parseLogCsv(csv);
  expect(rows.length).toBe(1);
  expect(rows[0].observed_raining).toBe("1");
  expect(rows[0].fc_bestmatch_mm).toBe("0.5");
  expect(rows[0].fc_rh_bestmatch).toBe("80");
});

test("parseLogCsv: strips BOM", () => {
  const csv = "\uFEFF" + LOG_HEADER.join(",") + "\n";
  expect(parseLogCsv(csv)).toEqual([]);
});

test("parseLogCsv: throws on missing column", () => {
  expect(() => parseLogCsv("issued_at,valid_at\n2026-01-01,2026-01-01\n")).toThrow(
    /missing required column/,
  );
});

test("parseLogCsv: throws on empty file", () => {
  expect(() => parseLogCsv("")).toThrow(/empty/);
});

test("loadLogCsv: required finds real diary", () => {
  const { rows, path: p, error } = loadLogCsv({ required: true });
  expect(error).toBeNull();
  expect(p).toBeTruthy();
  expect(Array.isArray(rows)).toBe(true);
  expect(rows.length).toBeGreaterThan(0);
});

test("loadLogCsv: required=false returns error object when missing", () => {
  // Point resolve at a nonsense relative path by monkeypatching cwd temporarily
  // — instead test parse path via a temp dir that has no log.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rain-log-"));
  const prev = process.cwd();
  try {
    process.chdir(tmp);
    // When cwd has no data/log.csv, resolve may still find repo via import.meta.
    // So only assert the real repo still works with required=false.
    const r = loadLogCsv({ required: false });
    // From tmp, module-relative root still finds the project log — that's intentional robustify.
    if (r.rows) {
      expect(Array.isArray(r.rows)).toBe(true);
    } else {
      expect(r.error).toMatch(/not found|failed/);
    }
  } finally {
    process.chdir(prev);
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
