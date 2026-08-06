import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import vercel from '@astrojs/vercel';

// Static by default (every page is pre-rendered HTML, zero JS), but /api/nowcast
// opts into on-demand serverless via `export const prerender = false` so it can
// answer live lat/lon queries. Free on Vercel Hobby. Deployed on Vercel.
export default defineConfig({
  site: 'https://rain.ishannaik.com',
  integrations: [sitemap()],
  adapter: vercel(),
});
