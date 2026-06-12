/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#080d1a',
          800: '#0a1020',
          700: '#0d1526',
          600: '#111e35',
          500: '#1a2744',
          400: '#243555',
        },
        accent: {
          cyan: '#22d3ee',
          amber: '#f59e0b',
          green: '#10b981',
          red: '#ef4444',
          orange: '#f97316',
          purple: '#a78bfa',
          blue: '#3b82f6',
          teal: '#14b8a6',
        },
        text: {
          primary: '#e2e8f0',
          muted: '#64748b',
          dim: '#94a3b8',
        },
      },
      fontFamily: {
        sans: ['Sora', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
