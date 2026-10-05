/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 950: '#102738', 900: '#173449', 800: '#24465a' },
        mint: { 50: '#eef8f3', 100: '#dcf1e6', 700: '#087558' },
      },
    },
  },
  plugins: [],
}
