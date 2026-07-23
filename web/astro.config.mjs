import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";
import sitemap from "@astrojs/sitemap";

// `site` enables absolute canonical/og URLs and the sitemap.
export default defineConfig({
  site: "https://analizatusarras.es",
  integrations: [tailwind(), sitemap()],
});
