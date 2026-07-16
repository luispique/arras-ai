/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,ts}"],
  theme: {
    extend: {
      colors: {
        // Intercom-inspired system: cream canvas anchors, white lifts cards.
        canvas: "#f5f1ec",
        surface: { DEFAULT: "#ffffff", alt: "#ebe7e1" },
        hairline: { DEFAULT: "#d3cec6", soft: "#ebe7e1" },
        ink: {
          DEFAULT: "#111111",
          muted: "#626260",
          subtle: "#7b7b78",
          tertiary: "#9c9fa5",
        },
        fin: "#ff5600",
        danger: "#c41c1c",
        warn: "#b45309",
        success: "#0b9f3e",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        md: "8px",
        lg: "12px",
        xl: "16px",
        pill: "9999px",
      },
      maxWidth: { content: "1280px" },
      letterSpacing: {
        tightest: "-0.04em",
        tighter: "-0.02em",
      },
    },
  },
  plugins: [],
};
