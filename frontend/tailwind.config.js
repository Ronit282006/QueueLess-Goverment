/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Brand/navy scale (refined light palette)
        brand: {
          DEFAULT: 'var(--c-brand)',
          soft: 'var(--c-brand-soft)',
          strong: 'var(--c-brand-strong)',
          50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd',
          400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8',
          800: '#1e40af', 900: '#1e3a8a',
        },
        navy: {
          soft: 'var(--c-navy-soft)',
          ink: 'var(--c-navy-ink)',
          'ink-2': 'var(--c-navy-ink-2)',
          600: 'var(--c-surface2)',
          700: 'var(--c-surface)',
          800: 'var(--c-surface)',
          900: 'var(--c-surface)',
        },
        // Semantic tokens live as CSS variables so light/dark/high-contrast
        // switch in one place.
        surface: 'var(--c-surface)',
        surface2: 'var(--c-surface-2)',
        ink: {
          DEFAULT: 'var(--c-ink)',
          2: 'var(--c-ink-2)',
          3: 'var(--c-ink-3)',
        },
        line: 'var(--c-line)',
        ok: {
          DEFAULT: 'var(--c-ok)',
          soft: 'var(--c-ok-soft)',
        },
        warn: {
          DEFAULT: 'var(--c-warn)',
          soft: 'var(--c-warn-soft)',
        },
        alert: {
          DEFAULT: 'var(--c-alert)',
          soft: 'var(--c-alert-soft)',
        },
        info: {
          DEFAULT: 'var(--c-info)',
          soft: 'var(--c-info-soft)',
        },
      },
      fontFamily: {
        sans: [
          'Plus Jakarta Sans', 'Inter', 'Noto Sans Devanagari', 'Noto Sans Gujarati',
          'Segoe UI', 'system-ui', '-apple-system', 'Roboto', 'Noto Sans', 'sans-serif',
        ],
      },
      borderRadius: {
        sm: '10px',
        md: '14px',
        lg: '18px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,.05), 0 10px 28px -14px rgba(16,24,40,.16)',
        pop: '0 18px 50px -18px rgba(16,24,40,.35)',
        brand: '0 10px 22px -12px rgba(29,78,216,.75)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'fade-slide': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          from: { backgroundPosition: '-200% 0' }, to: { backgroundPosition: '200% 0' },
        },
        'pulse-soft': {
          '0%,100%': { boxShadow: '0 0 0 0 var(--dot-ring)' },
          '50%': { boxShadow: '0 0 0 5px transparent' },
        },
      },
      animation: {
        'fade-in': 'fade-in .18s ease-out',
        'fade-slide': 'fade-slide .22s ease-out both',
        shimmer: 'shimmer 1.4s linear infinite',
        'pulse-soft': 'pulse-soft 2s ease-out infinite',
      },
    },
  },
  plugins: [],
}