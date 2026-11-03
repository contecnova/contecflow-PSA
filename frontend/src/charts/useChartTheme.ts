import { useEffect, useState } from 'react'

/** Dark themes as defined in index.css [data-theme] */
const DARK_THEMES = new Set(['freight', 'high-contrast', 'midnight', 'slate', 'dark', 'system'])

export interface ChartThemeTokens {
  text1: string
  text2: string
  text3: string
  surface0: string
  surface1: string
  surface2: string
  surface3: string
  surface4: string
  accent: string
  success: string
  danger: string
  warning: string
  info: string
  textColor?: string
  tooltipBg?: string
  primary?: string
}

export interface ChartThemeState {
  dark: boolean
  tokens: ChartThemeTokens
}

/** CSS variable tokens resolved from the current :root */
function resolveTokens(): ChartThemeTokens {
  const style = getComputedStyle(document.documentElement)
  const get = (v: string): string => style.getPropertyValue(v).trim()
  return {
    text1:    get('--text-1')    || '#f2f2f2',
    text2:    get('--text-2')    || '#c3c7cf',
    text3:    get('--text-3')    || '#8f97a3',
    surface0: get('--surface-0') || '#0a0b0f',
    surface1: get('--surface-1') || '#17191e',
    surface2: get('--surface-2') || '#1f2228',
    surface3: get('--surface-3') || '#2a2e36',
    surface4: get('--surface-4') || '#3a3f49',
    accent:   get('--accent')    || '#caa34c',
    success:  get('--success')   || '#59c08c',
    danger:   get('--danger')    || '#e68b8b',
    warning:  get('--warning')   || '#d5a441',
    info:     get('--info')      || '#77b5ff',
    textColor: get('--text-2')   || '#c3c7cf',
    tooltipBg: get('--surface-2') || '#1f2228',
    primary:   get('--accent')    || '#caa34c',
  }
}

function isDark(): boolean {
  const theme = document.documentElement.getAttribute('data-theme') || 'freight'
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  return DARK_THEMES.has(theme)
}

/**
 * Returns { dark: boolean, tokens: { text1, text2, ..., surface0–4, accent, ... } }
 * Reacts to [data-theme] attribute mutations.
 */
export function useChartTheme(): ChartThemeState {
  const [state, setState] = useState<ChartThemeState>(() => ({ dark: isDark(), tokens: resolveTokens() }))

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setState({ dark: isDark(), tokens: resolveTokens() })
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  return state
}
