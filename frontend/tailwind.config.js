/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        ink: '#1d2623',
        paper: '#f7f4ed',
        cinnabar: '#ba3b2d',
        jade: '#226957',
        gold: '#c99643',
      },
      boxShadow: {
        soft: '0 18px 60px rgba(25, 35, 31, 0.08)',
      },
    },
  },
  plugins: [],
}
