import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // PM Copilot dark theme palette
        background: "hsl(222, 47%, 6%)",
        foreground: "hsl(210, 40%, 98%)",
        card: {
          DEFAULT: "hsl(222, 47%, 9%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        primary: {
          DEFAULT: "hsl(217, 91%, 60%)",
          foreground: "hsl(222, 47%, 6%)",
        },
        secondary: {
          DEFAULT: "hsl(217, 33%, 17%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        muted: {
          DEFAULT: "hsl(217, 33%, 17%)",
          foreground: "hsl(215, 20%, 65%)",
        },
        accent: {
          DEFAULT: "hsl(217, 33%, 17%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        destructive: {
          DEFAULT: "hsl(0, 63%, 31%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        border: "hsl(217, 33%, 17%)",
        input: "hsl(217, 33%, 17%)",
        ring: "hsl(217, 91%, 60%)",
        // Agent status colors
        agent: {
          pending: "hsl(215, 20%, 45%)",
          running: "hsl(217, 91%, 60%)",
          completed: "hsl(142, 71%, 45%)",
          failed: "hsl(0, 84%, 60%)",
        },
      },
      borderRadius: {
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.25rem",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.5s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
