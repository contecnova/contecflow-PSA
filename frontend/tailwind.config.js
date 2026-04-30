/** @type {import('tailwindcss').Config} */
// Source of truth for color/spacing/typography tokens lives in src/index.css
// (CSS custom properties). Tailwind here only contributes a few breakpoints
// and font families — colors are intentionally NOT defined here to avoid
// drifting from the CSS token system.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      screens: {
        xs: '320px',
        sm: '480px',
      },
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['Geist Mono', 'Space Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
