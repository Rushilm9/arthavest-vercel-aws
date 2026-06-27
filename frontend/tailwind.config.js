/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      screens: {
        // Extra-small breakpoint for narrow phones (default Tailwind starts at sm:640px)
        xs: "400px",
      },
      colors: {
        cream: "#F0F4F8", // backdrop light ice-blue
        card: "#FFFFFF",
        primary: "#1C2A39", // Dark Navy Blue primary text & headings
        muted: "#5A6E85",   // Steel Blue muted text
        navy: {
          DEFAULT: "#1C2A39",
          light: "#2E3E50",
          soft: "#EAF1F9",
        },
        accent: {
          DEFAULT: "#B85A10", // Golden Saffron accent from logo
          dark: "#9A4B0E",
          soft: "#FFF6EB",
        },
        signal: {
          buy: "#16A34A",
          sell: "#DC2626",
          wait: "#B85A10",
          hold: "#5A6E85",
        },
        border: {
          DEFAULT: "#E2E8F0",
          buy: "#86EFAC",
          sell: "#FCA5A5",
        }
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "spin-slow": "spin 3s linear infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
