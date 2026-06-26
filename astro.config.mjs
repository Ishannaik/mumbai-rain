import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Static output (default) — zero JS unless an island opts in. Builds to dist/.
// Deployed on Vercel ($0 static; auto-deploys on git push to main).
export default defineConfig({
  site: 'https://mumbai-rain.vercel.app',
  integrations: [sitemap()],
});
