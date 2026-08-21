import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import vercel from '@astrojs/vercel';
import sentry from '@sentry/astro';

// Static by default (every page is pre-rendered HTML, zero JS), but /api/nowcast
// opts into on-demand serverless via `export const prerender = false` so it can
// answer live lat/lon queries. Free on Vercel Hobby. Deployed on Vercel.
//
// Sentry: enabled only when PUBLIC_SENTRY_DSN is set (Vercel env vars). Without
// it the integration no-ops, so local dev and CI stay clean and free.
export default defineConfig({
  site: 'https://rain.ishannaik.com',
  integrations: [
    sitemap(),
    ...(process.env.PUBLIC_SENTRY_DSN ? [sentry()] : []),
  ],
  adapter: vercel(),
});
