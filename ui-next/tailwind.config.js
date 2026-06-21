/* eslint-disable @typescript-eslint/no-require-imports */
/** @type {import('tailwindcss').Config} */
const plugin = require('tailwindcss/plugin');

module.exports = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Core Palette mapped to CSS Variables
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        'surface-3': 'var(--surface-3)',
        'surface-hover': 'var(--surface-hover)',
        
        text: 'var(--text)',
        'text-2': 'var(--text-2)',
        'text-muted': 'var(--text-muted)',
        'text-subtle': 'var(--text-subtle)',
        
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
        
        accent: 'var(--accent)',
        'accent-hover': 'var(--accent-hover)',
        'accent-dim': 'var(--accent-dim)',
        'accent-2': 'var(--accent-2)',
        
        red: 'var(--red)',
        
        // Legacy / Compatibility mapping (can be phased out)
        'mds-color-hcp-brand': 'var(--text)',
        'mds-color-dark-charcoal': 'var(--bg)',
        'mds-color-near-black': 'var(--surface)',
        'mds-color-light-gray': 'var(--surface-2)',
        'mds-color-mid-gray': 'var(--text-muted)',
        'mds-color-cool-gray': 'var(--text-subtle)',
        'mds-color-dark-gray': 'var(--text-subtle)',
        'mds-color-charcoal': 'var(--surface-3)',
        'mds-color-near-white': 'var(--text)',
        'mds-color-action-blue': 'var(--accent)',
        'mds-color-vagrant-brand': 'var(--accent)',
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': 'var(--text-2xs)',
        'xs': 'var(--text-xs)',
        'sm': 'var(--text-sm)',
        'base': 'var(--text-base)',
        'md': 'var(--text-md)',
        'lg': 'var(--text-lg)',
        'xl': 'var(--text-xl)',
        '2xl': 'var(--text-2xl)',
        '3xl': 'var(--text-3xl)',
        '4xl': 'var(--text-4xl)',
        '5xl': 'var(--text-5xl)',
        '6xl': 'var(--text-6xl)',
      },
      borderRadius: {
        'DEFAULT': 'var(--radius)',
        'lg': 'var(--radius)',
        'xl': 'calc(var(--radius) * 1.5)',
      },
      boxShadow: {
        'sm': 'var(--shadow)',
        'lg': 'var(--shadow-lg)',
        'accent': 'var(--accent-glow)',
      },
    },
  },
  plugins: [
    plugin(function({ addUtilities }) {
      addUtilities({
        '.glass': {
          '@apply bg-surface/70 backdrop-blur-xl border border-border': {},
        },
      });
    }),
  ],
};
