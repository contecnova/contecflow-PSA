/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#e6fcff',
          100: '#b3f5ff',
          500: '#00d4ff',
          600: '#00aad4',
          900: '#003d4d',
        },
        surface: {
          DEFAULT: '#111827',
          alt: '#1a2235',
          border: '#1e2d45',
        },
      },
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['Space Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
