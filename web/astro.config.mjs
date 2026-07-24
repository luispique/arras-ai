import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

// `site` enables absolute canonical/og URLs. The sitemap is a static file in
// public/ (a 4-page fixed site doesn't need the @astrojs/sitemap integration,
// which is also incompatible with this Astro version).
export default defineConfig({
  site: "https://analizatusarras.es",
  integrations: [tailwind()],
});
