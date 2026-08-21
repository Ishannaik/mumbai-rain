// log-csv.js — robust build-time reader for data/log.csv (the training diary).
// Used by the scoreboard so a missing/unreadable log FAILS THE BUILD instead of
// shipping a silent "Couldn't read the log" empty state that the SW can cache.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Expected header — must stay in lockstep with pipeline/log_snapshot.LOG_HEADER. */
export const LOG_HEADER = [
  "issued_at",
  "valid_at",
  "lat",
  "lon",
  "fc_bestmatch_mm",
  "fc_ecmwf_mm",
  "fc_rh_bestmatch",
  "hour",
  "recent_rain_mm",
  "observed_raining",
];

/**
 * Candidate project roots. `process.cwd()` is correct for `astro build` / Vercel,
 * but we also walk from this module so local odd cwd / monorepo layouts still work.
 */
export function projectRoots() {
  const roots = [process.cwd()];
  try {
    // this file lives at src/lib → repo root is ../..
    roots.push(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../.."));
  } catch {
    // import.meta.url unavailable — cwd only
  }
  // de-dupe, keep order
  return [...new Set(roots.map((r) => path.normalize(r)))];
}

/** Resolve the first existing file under any project root. */
export function resolveRepoFile(...parts) {
  const tried = [];
  for (const root of projectRoots()) {
    const p = path.join(root, ...parts);
    tried.push(p);
    try {
      if (fs.existsSync(p) && fs.statSync(p).isFile()) {
        return { path: p, tried };
      }
    } catch {
      // keep trying
    }
  }
  return { path: null, tried };
}

/**
 * Parse log.csv text into row objects. Throws on malformed header.
 * Empty diary (header only) → [].
 */
export function parseLogCsv(raw) {
  if (raw == null) throw new Error("parseLogCsv: raw is null/undefined");
  const text = String(raw).replace(/^\uFEFF/, ""); // strip BOM if present
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) {
    throw new Error("parseLogCsv: file is empty (no header)");
  }
  const header = lines[0].split(",").map((h) => h.trim());
  for (const col of LOG_HEADER) {
    if (!header.includes(col)) {
      throw new Error(
        `parseLogCsv: missing required column "${col}". Got: ${header.join(",")}`,
      );
    }
  }
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    /** @type {Record<string, string>} */
    const o = {};
    header.forEach((h, i) => {
      o[h] = (cells[i] ?? "").trim();
    });
    return o;
  });
}

/**
 * Load and parse data/log.csv from the repo.
 * @param {{ required?: boolean }} [opts]
 *   required (default true): throw if missing/unreadable — build fails loudly.
 *   When required=false, returns { rows: null, error, tried } instead of throwing.
 */
export function loadLogCsv(opts = {}) {
  const required = opts.required !== false;
  const { path: logPath, tried } = resolveRepoFile("data", "log.csv");

  if (!logPath) {
    const msg =
      `scoreboard/log: data/log.csv not found.\n` +
      `  cwd=${process.cwd()}\n` +
      `  tried:\n    - ${tried.join("\n    - ")}`;
    if (required) throw new Error(msg);
    return { rows: null, path: null, tried, error: msg };
  }

  try {
    const raw = fs.readFileSync(logPath, "utf8");
    const rows = parseLogCsv(raw);
    return { rows, path: logPath, tried, error: null };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    const msg = `scoreboard/log: failed reading ${logPath}: ${detail}`;
    if (required) throw new Error(msg);
    return { rows: null, path: logPath, tried, error: msg };
  }
}

/**
 * Load public/model.json (optional — scoreboard can show raw stats without it).
 */
export function loadModelJson() {
  const { path: modelPath, tried } = resolveRepoFile("public", "model.json");
  if (!modelPath) {
    return { model: null, path: null, tried, error: "model.json not found" };
  }
  try {
    const model = JSON.parse(fs.readFileSync(modelPath, "utf8"));
    return { model, path: modelPath, tried, error: null };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return {
      model: null,
      path: modelPath,
      tried,
      error: `model.json parse failed: ${detail}`,
    };
  }
}
