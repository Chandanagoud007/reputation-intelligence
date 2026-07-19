/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          teal:   "#0F6E56",
          purple: "#3C3489",
          coral:  "#993C1D",
          amber:  "#854F0B",
        }
      }
    },
  },
  plugins: [],
}