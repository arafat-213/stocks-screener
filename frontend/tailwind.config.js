/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        background: 'var(--color-bg)',
        'bg-secondary': 'var(--color-bg-secondary)',
        'bg-elevated': 'var(--color-bg-elevated)',
        text: 'var(--color-text)',
        'text-muted': 'var(--color-text-muted)',
        border: 'var(--color-border)',
        primary: 'rgb(var(--color-primary-rgb) / <alpha-value>)',
        bullish: 'rgb(var(--color-bullish-rgb) / <alpha-value>)',
        bearish: 'rgb(var(--color-bearish-rgb) / <alpha-value>)',
        warning: 'rgb(var(--color-warning-rgb) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['var(--font-main)', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      borderRadius: {
        xl: 'var(--radius-xl)',
        lg: 'var(--radius-lg)',
        md: 'var(--radius-md)',
        sm: 'var(--radius-sm)',
      },
      animation: {
        spin: 'spin 1s linear infinite',
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'zoom-in': 'zoomIn 0.2s ease-out',
        'skeleton-loading': 'skeleton-loading 1.5s infinite linear',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(100%)' },
          '100%': { transform: 'translateY(0)' },
        },
        zoomIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        'skeleton-loading': {
          '0%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
      },
    },
  },
  plugins: [],
};
