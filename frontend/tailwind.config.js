/** @type {import('tailwindcss').Config} */

// Brand ramp built around #CF1FA4.
//
// Contrast, checked against white:
//   500 (#CF1FA4) → 4.78:1  passes AA for normal text (links, button labels)
//   700 (#8E1372) → 8.45:1  passes AAA (use this for coloured body text)
//
// Use 500 only for things you can act on: primary buttons, links, active
// states, one chart accent. Body copy stays `ink`. The colour is highly
// saturated and reads as loud at scale.
const brand = {
  50: "#FDF2FA", // card tints, hover states
  100: "#FAE3F4", // upload zone fill
  200: "#EFC0E4", // borders, dashed outlines
  300: "#E196CE",
  400: "#D95CB8",
  500: "#CF1FA4", // primary actions, links, active states
  600: "#B01A8C", // hover on primary
  700: "#8E1372", // text on tint
};

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand,
        // `blush` is an alias of the same ramp so existing components that
        // reference blush-* recolour without edits. Prefer `brand` in new
        // code; this alias can be removed once nothing references it.
        blush: brand,
        ink: {
          DEFAULT: "#2B2730",
          muted: "#6B6570",
          faint: "#A79FA9",
        },
        sage: {
          50: "#F1F5F1",
          500: "#6B9080",
          600: "#557567",
        },
      },
      fontFamily: {
        display: ["Fraunces", "ui-serif", "Georgia", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(43, 39, 48, 0.04), 0 8px 24px -8px rgba(43, 39, 48, 0.10)",
        card: "0 1px 3px rgba(43, 39, 48, 0.06), 0 12px 32px -12px rgba(207, 31, 164, 0.18)",
      },
      keyframes: {
        indeterminate: {
          "0%": { transform: "translateX(-60%)" },
          "100%": { transform: "translateX(160%)" },
        },
      },
      animation: {
        indeterminate: "indeterminate 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};