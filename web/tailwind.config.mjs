/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,ts}"],
  theme: {
    extend: {
      colors: {
        // Botpress 2025 Light: warm off-white base, near-black ink, flat & editorial.
        canvas: "#e8ebe6", // brand-base — page background
        warm: "#f1f0ea", // earth-warm — nav frosted tint base
        surface: { DEFAULT: "#f6f7f6", alt: "#e0e2dc" }, // surface-light + a slightly deeper alt
        ink: {
          DEFAULT: "#09090b", // near-black — primary text, CTA fill
          soft: "#222222",
          mid: "#626762", // secondary/muted body
          muted: "#a1a5a0", // borders, tertiary
        },
        // Semantic accents for risk levels (tuned to sit on the warm base).
        danger: "#b42318",
        warn: "#b45309",
        success: "#2e7d4f",
      },
      fontFamily: {
        // Kameron (serif display) + Aspekta (the design's geometric sans, OFL, self-hosted).
        serif: ["Kameron", "Georgia", "Times New Roman", "serif"],
        sans: ["Aspekta", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        pill: "9999px", // fully-pill CTAs (spec's ~16080px = fully rounded)
        xl: "20px",
        lg: "16px",
        md: "12px",
        sm: "8px",
        xs: "4px",
      },
      maxWidth: { content: "1200px", prose: "44rem" },
      letterSpacing: {
        tightest: "-0.03em",
        tighter: "-0.02em",
        label: "0.08em",
      },
      boxShadow: {
        // The single validated shadow token from the spec.
        subtle: "0px 2px 10px 0px rgba(0,0,0,0.1)",
      },
    },
  },
  plugins: [],
};
