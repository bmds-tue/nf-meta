import type { ThemeDefinition } from 'vuetify'

// Every color the editor uses is a theme color, so themes differ only here.
//   background   graph canvas            surface      cards, app bar, menus
//   panel        sidebar background      node*        graph nodes
//   edge         edges between steps     grid         canvas dots
//   handle       node connection handles
// Inputs keep one purple everywhere (INPUT_COLOR) and nf-core its green.

const nfcore = '#24B064'

const light: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#efefef',
    surface: '#2d3748',
    surfaceVariant: '#0a7652',
    panel: '#4a9479',
    primary: '#2563eb',
    primarySoft: '#5e88e3',
    success: '#16a34a',
    warning: '#f59e0b',
    error: '#dc2626',
    info: '#38bdf8',
    nodeBackground: '#efefef',
    nodeText: '#303030',
    nodeDefaultBorder: '#925819',
    nodeNfCoreBorder: '#1a9655',
    nfcore,
    edge: '#2d3748',
    grid: '#81818a',
    handle: '#2d3f46',
    onSurface: '#cbd5e1',
    onBackground: '#303030',
    onPrimary: '#ffffff',
  },
}

// A: the current look carried over to dark: slate blues, blue accent
const slate: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0f172a',
    surface: '#1e293b',
    surfaceVariant: '#273449',
    panel: '#162033',
    primary: '#3b82f6',
    primarySoft: '#2b5fb8',
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444',
    info: '#38bdf8',
    nodeBackground: '#1e293b',
    nodeText: '#e2e8f0',
    nodeDefaultBorder: '#c2873a',
    nodeNfCoreBorder: '#22a565',
    nfcore,
    edge: '#94a3b8',
    grid: '#334155',
    handle: '#64748b',
    onSurface: '#e2e8f0',
    onBackground: '#cbd5e1',
    onPrimary: '#ffffff',
  },
}

// B: neutral greys like a code editor, nf-core green as the accent
const graphite: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0c0c0c',
    surface: '#232323',
    surfaceVariant: '#333333',
    panel: '#181818',
    primary: nfcore,
    primarySoft: '#1d7a49',
    success: '#4ade80',
    warning: '#fbbf24',
    error: '#f87171',
    info: '#38bdf8',
    nodeBackground: '#262626',
    nodeText: '#f5f5f5',
    nodeDefaultBorder: '#d6a85c',
    nodeNfCoreBorder: '#2cc472',
    nfcore,
    edge: '#b4b9c2',
    grid: '#3a3a3a',
    handle: '#9aa0a8',
    onSurface: '#f2f2f2',
    onBackground: '#e0e0e0',
    onPrimary: '#0b0b0b',
  },
}

// C: deep navy with a violet accent, closest to the input purple; the highest contrast
const midnight: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0a0d1a',
    surface: '#151a30',
    surfaceVariant: '#1f2542',
    panel: '#10142a',
    primary: '#8b5cf6',
    primarySoft: '#6d48d6',
    success: '#34d399',
    warning: '#fbbf24',
    error: '#fb7185',
    info: '#60a5fa',
    nodeBackground: '#151a30',
    nodeText: '#eceefb',
    nodeDefaultBorder: '#e0a04a',
    nodeNfCoreBorder: '#2fbf71',
    nfcore,
    edge: '#7f8bbd',
    grid: '#1e2442',
    handle: '#5a6496',
    onSurface: '#eceefb',
    onBackground: '#c9cdea',
    onPrimary: '#ffffff',
  },
}

export const THEMES = { light, slate, graphite, midnight }
export type ThemeName = keyof typeof THEMES

export const THEME_CHOICES: { name: ThemeName, title: string, subtitle: string }[] = [
  { name: 'slate', title: 'Dark: Slate', subtitle: 'Slate blues, blue accent' },
  { name: 'graphite', title: 'Dark: Graphite', subtitle: 'Neutral greys, nf-core green' },
  { name: 'midnight', title: 'Dark: Midnight', subtitle: 'Deep navy, violet accent' },
  { name: 'light', title: 'Light', subtitle: 'Light canvas, dark cards' },
]

export const DEFAULT_THEME: ThemeName = 'slate'
const STORAGE_KEY = 'theme'

/** The theme picked in this browser, or the default (dark). */
export function storedTheme(): ThemeName {
  try {
    const name = localStorage.getItem(STORAGE_KEY)
    return name && name in THEMES ? name as ThemeName : DEFAULT_THEME
  } catch {
    return DEFAULT_THEME
  }
}

export function storeTheme(name: ThemeName) {
  try {
    localStorage.setItem(STORAGE_KEY, name)
  } catch {
    // private window or blocked storage: the choice just isn't remembered
  }
}
