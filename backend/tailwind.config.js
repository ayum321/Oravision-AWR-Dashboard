/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./templates/**/*.html'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        dark: { 900: '#0b0f1a', 800: '#111827', 700: '#1e293b', 600: '#334155' },
        accent: '#06b6d4',
      },
    },
  },
  plugins: [],
}
