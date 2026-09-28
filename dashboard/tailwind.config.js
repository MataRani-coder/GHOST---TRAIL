/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Brand
        accent:       '#F97316',
        'accent-dim': '#C05B10',
        'accent-glow':'rgba(249,115,22,0.15)',
        // Cyan
        cyan:         '#06B6D4',
        'cyan-glow':  'rgba(6,182,212,0.12)',
        // Status
        danger:       '#EF4444',
        'danger-glow':'rgba(239,68,68,0.14)',
        success:      '#10B981',
        amber:        '#F59E0B',
        // Dark palette
        'panel':      '#0D1117',
        'card':       '#161B22',
        'card-border':'#21262D',
        'sidebar':    '#0B0F14',
        'sidebar-hover':'#161B22',
        'sidebar-active':'#1C2230',
        // Text
        'text-primary':'#E6EDF3',
        'text-muted':  '#7D8590',
        'text-dim':    '#484F58',
        // Legacy compat
        charcoal:     '#E6EDF3',
        'charcoal-light':'#7D8590',
        divider:      '#21262D',
        'bg-warm':    '#0D1117',
        'bg-card':    '#161B22',
      },
      fontFamily: {
        sans:    ['"Inter"', 'system-ui', 'sans-serif'],
        heading: ['"Rajdhani"', 'sans-serif'],
        mono:    ['"Share Tech Mono"', '"Courier New"', 'monospace'],
      },
      animation: {
        'pulse-fast':   'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-slow':   'pulse 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer':      'shimmer 2s infinite linear',
        'scan':         'scan 4s linear infinite',
        'blink':        'blink 1.2s step-start infinite',
        'glow-pulse':   'glowPulse 2s ease-in-out infinite',
        'fade-in':      'fadeIn 0.3s ease forwards',
        'slide-up':     'slideUp 0.4s cubic-bezier(0.16,1,0.3,1) forwards',
      },
      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        scan: {
          '0%':   { backgroundPosition: '0 -100%' },
          '100%': { backgroundPosition: '0 200%' },
        },
        blink: {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0' },
        },
        glowPulse: {
          '0%,100%': { boxShadow: '0 0 8px rgba(249,115,22,0.3)' },
          '50%':     { boxShadow: '0 0 22px rgba(249,115,22,0.65)' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.6)',
        'card-hover': '0 0 0 1px rgba(6,182,212,0.35), 0 4px 24px rgba(6,182,212,0.08)',
        'glow-orange': '0 0 20px rgba(249,115,22,0.4)',
        'glow-cyan':   '0 0 20px rgba(6,182,212,0.3)',
        'glow-red':    '0 0 20px rgba(239,68,68,0.3)',
      },
    },
  },
  plugins: [],
}
