/* ── Color tokens ──────────────────────────────────────────────
   Centralised so we can tweak the look in one place.
   Follows a simple naming convention:
     bg-*  = background shades
     fg-*  = foreground / text shades
     team-* = team-specific colours
     accent-* = semantic accents (heal, damage, crit, etc.)
   ───────────────────────────────────────────────────────────── */

export const theme = {
  /* Backgrounds */
  bg: {
    page: '#1a1a1a',
    panel: '#1e1e1e',
    surface: '#222',
    surfaceRaised: '#2a2a2a',
    surfaceHover: '#333',
    card: '#1a1a2a',
    grid: '#e8e8e8',
    gridCell: '#ffffff',
    gridCellHover: '#f0f8ff',
    roster: '#f8f8f8',
    overlay: 'rgba(0, 0, 0, 0.6)',
  },

  /* Foreground / text */
  fg: {
    primary: '#eee',
    secondary: '#ccc',
    muted: '#aaa',
    dim: '#888',
    disabled: '#555',
    placeholder: '#666',
    bright: '#ffffff',
  },

  /* Teams */
  team: {
    0: '#4488ff',
    1: '#ff4444',
    '0light': '#66aaff',
    '1light': '#ff7777',
  },

  /* Accents */
  accent: {
    primary: '#28a745',
    warning: '#cc7a00',
    danger: '#c00',
    gold: '#ffd700',
    hit: '#ff4444',
    crit: '#ffd700',
    miss: '#ff6666',
    ability: '#6cf',
    modifier: '#ca0',
  },

  /* HP thresholds */
  hp: {
    high: '#4c4',
    mid: '#fa0',
    low: '#f66',
    dead: '#666',
  },

  borders: {
    subtle: '#333',
    muted: '#444',
    light: '#555',
    gridLine: '#ccc',
    gridBorder: '#aaa',
  },
} as const;

export type Theme = typeof theme;
