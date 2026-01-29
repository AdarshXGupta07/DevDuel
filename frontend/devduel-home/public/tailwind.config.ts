/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      animation: {
        gridMove: "gridMove 20s linear infinite",
        floatSlow: "floatSlow 12s ease-in-out infinite",
        floatFast: "floatFast 8s ease-in-out infinite",
      },
      keyframes: {
        gridMove: {
          "0%": { backgroundPosition: "0 0" },
          "100%": { backgroundPosition: "600px 600px" },
        },
        floatSlow: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-40px)" },
        },
        floatFast: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-70px)" },
        },
      },
    },
  },
  plugins: [],
};
