import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // AMD brand palette
        amd: {
          red: "#ED1C24",
          dark: "#1A1A1A",
        },
        // Status colors
        healthy: "#22c55e",
        warning: "#f59e0b",
        "at-risk": "#f97316",
        critical: "#ef4444",
        offline: "#6b7280",
        // Dark NOC theme
        background: "#0f172a",
        surface: "#1e293b",
        "surface-2": "#334155",
        border: "#475569",
        "text-primary": "#f1f5f9",
        "text-secondary": "#94a3b8",
        "text-muted": "#64748b",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-in",
        "slide-in": "slideIn 0.2s ease-out",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideIn: { "0%": { transform: "translateY(-8px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
      },
    },
  },
  plugins: [],
} satisfies Config;
