// Turn a locality name into a clean URL slug for the SEO pages.
//   "Bandra"              -> "bandra"
//   "Lower Parel"         -> "lower-parel"
//   "Vashi (Navi Mumbai)" -> "vashi"   (parenthetical dropped)
export const slugify = (name) =>
  name
    .toLowerCase()
    .replace(/\(.*?\)/g, "")          // drop parentheticals
    .replace(/[^a-z0-9]+/g, "-")      // non-alphanumerics -> hyphen
    .replace(/^-+|-+$/g, "");         // trim leading/trailing hyphens
