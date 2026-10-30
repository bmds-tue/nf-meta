import type { ThemeDefinition } from 'vuetify'

// Every color the editor uses is a theme color, so themes differ only here.
//   background   graph canvas            surface      cards, app bar, menus
//   panel        sidebar background      node*        graph nodes
//   edge         edges between steps     grid         canvas dots
//   handle       node connection handles
//   nodeHover / nodeSelected   rings around hovered and selected nodes
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
    nodeHover: '#64748b',
    nodeSelected: '#2563eb',
    onSurface: '#cbd5e1',
    onBackground: '#303030',
    onPrimary: '#ffffff',
  },
}

// Dark: neutral greys like a code editor, nf-core green as the accent
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
    grid: '#585858',
    handle: '#9aa0a8',
    nodeHover: '#8a8f98',
    nodeSelected: '#ffffff',
    onSurface: '#f2f2f2',
    onBackground: '#e0e0e0',
    onPrimary: '#0b0b0b',
  },
}

export const THEMES = { light, graphite }
export type ThemeName = keyof typeof THEMES

export const DARK_THEME: ThemeName = 'graphite'
export const LIGHT_THEME: ThemeName = 'light'
const STORAGE_KEY = 'theme'

/** The theme picked in this browser, or the default (dark). */
export function storedTheme(): ThemeName {
  try {
    const name = localStorage.getItem(STORAGE_KEY)
    return name && name in THEMES ? name as ThemeName : DARK_THEME
  } catch {
    return DARK_THEME
  }
}

export function storeTheme(name: ThemeName) {
  try {
    localStorage.setItem(STORAGE_KEY, name)
  } catch {
    // private window or blocked storage: the choice just isn't remembered
  }
}
