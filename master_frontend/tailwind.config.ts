import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        navy: { 900: "#0d1117", 800: "#161b22", 700: "#1c2230", 600: "#243044" },
      },
    },
  },
  plugins: [],
};

export default config;
