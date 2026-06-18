/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Playfair Display"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
      },
      colors: {
        canvas: "#f8fafc",
        navy: "#0f172a",
        slate: "#1e293b",
        amber: { legal: "rgba(217, 119, 6, 0.25)" },
      },
      boxShadow: {
        dock: "0 8px 32px rgba(15, 23, 42, 0.12)",
      },
    },
  },
  plugins: [],
};
