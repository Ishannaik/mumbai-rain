import { defineConfig } from 'astro/config';

// Static output (default) — zero JS unless an island opts in. Builds to dist/.
// Cloudflare Pages runs `npm run build`; $0 hosting, robust.
export default defineConfig({
  site: 'https://mumbai-rain.pages.dev',
});
