/**
 * theme.ts — Design tokens centralizados de Contecflow
 *
 * REGLA: Nunca uses colores hex directamente en componentes.
 * - En CSS/JSX inline: usa var(--accent), var(--surface-2), etc.
 * - En Recharts/SVG: COLOR.* (son var(--x)) o CHART_COLORS para series.
 * - En Canvas, donde var() no se resuelve: getCSSVar('--x').
 *
 * Las CSS vars están definidas en src/index.css
 */

import type { CSSProperties } from 'react'

// ── Helper: leer CSS var en runtime (para Recharts donde CSS vars no aplican) ──
/**
 * getAccent() — Lee --accent del DOM en tiempo real.
 * Úsalo en componentes que se re-renderizan cuando cambia el tema.
 * Ejemplo en Recharts: stroke={getAccent()}
 */
export function getAccent(): string {
  if (typeof window === 'undefined') return '#4f8ef7'
  return getComputedStyle(document.documentElement)
    .getPropertyValue('--accent').trim() || '#4f8ef7'
}

export function getCSSVar(varName: string, fallback: string = ''): string {
  if (typeof window === 'undefined') return fallback
  return getComputedStyle(document.documentElement)
    .getPropertyValue(varName).trim() || fallback
}

// ── Colores del sistema ────────────────────────────────────────────────────────
// Cada valor es la variable CSS, no una copia de su valor: así sigue al tema
// activo y al acento del perfil. Sirve en style={{}} y en fill/stroke de SVG.
// En canvas, o donde var() no se resuelva, getCSSVar('--x').
// Para opacidad, alpha(COLOR.x, '20'): pegar '20' a un var() da CSS inválido.
export const COLOR = {
  // Superficies (de más oscuro a más claro)
  surface0:    'var(--surface-0)',
  surface1:    'var(--surface-1)',
  surface2:    'var(--surface-2)',
  surface3:    'var(--surface-3)',
  surface4:    'var(--surface-4)',
  surface5:    'var(--surface-5)',

  // Jerarquía de texto
  text1:       'var(--text-1)',   // headings, valores clave
  text2:       'var(--text-2)',   // labels, descripciones
  text3:       'var(--text-3)',   // secundario, pistas
  text4:       'var(--text-4)',   // decorativo: nunca texto que haya que leer

  // Accent
  accent:      'var(--accent)',
  accentDim:   'var(--accent-dim)',
  accentGlow:  'var(--accent-glow)',
  accentMuted: 'var(--accent-muted)',

  // Semánticos
  success:       'var(--success)',
  successBg:     'var(--success-bg)',
  successBorder: 'var(--success-border)',
  warning:       'var(--warning)',
  warningBg:     'var(--warning-bg)',
  warningBorder: 'var(--warning-border)',
  danger:        'var(--danger)',
  dangerBg:      'var(--danger-bg)',
  dangerBorder:  'var(--danger-border)',
  info:          'var(--info)',
  infoBg:        'var(--info-bg)',
  orange:        'var(--orange)',   // severidad alta (P2), distinta del aviso

  // Purple — AI / features premium
  purple:    'var(--purple)',
  purpleBg:  'var(--purple-bg)',
} as const

/**
 * alpha() — un color con opacidad, válido para un hex y para var(--x).
 * `'var(--success)' + '20'` es CSS inválido y el navegador descarta la
 * propiedad entera; color-mix() admite los dos. Un hex de 6 cifras da lo de
 * siempre (#rrggbb + aa). hexAlpha va de '00' a 'ff'.
 */
export function alpha(color: string | null | undefined, hexAlpha: string): string {
  if (!color) return ''
  if (/^#[0-9a-fA-F]{6}$/.test(color)) return color + hexAlpha
  const pct = Math.round((parseInt(hexAlpha, 16) / 255) * 100)
  return `color-mix(in srgb, ${color} ${pct}%, transparent)`
}

export type ColorToken = keyof typeof COLOR

/**
 * Color inicial de los selectores de color de datos (tipos de incidencia,
 * flujos, roles, tipos de tiempo). Es un DATO que se guarda en la API, no un
 * estilo: `<input type="color">` sólo acepta `#rrggbb` y la API valida ese
 * formato, así que aquí un `var(--x)` no sirve. Hex a propósito.
 */
export const COLOR_DATO_POR_DEFECTO = '#7a8aaa'

// ── Paleta secuencial para gráficos ───────────────────────────────────────────
// Usar en Recharts, Chart.js, D3, SVG donde CSS vars no aplican
// ── Paleta extendida para gráficos con más series ────────────────────────────
// Usar en orden: para 8+ series en Recharts, CumulativeFlow, etc.
export const CHART_COLORS_EXTENDED: readonly string[] = [
  '#4f8ef7',  // accent blue
  '#34d399',  // success green
  '#f59e0b',  // warning amber
  '#a78bfa',  // purple
  '#2dd4bf',  // teal
  '#f87171',  // danger red
  '#fb923c',  // orange
  '#e879f9',  // fuchsia
  '#84cc16',  // lime
  '#ec4899',  // pink
  '#38bdf8',  // sky
  '#a3e635',  // yellow-green
] as const

export const CHART_COLORS: readonly string[] = [
  '#4f8ef7',       // [0] azul índigo
  '#34d399',       // [1] verde esmeralda
  '#f59e0b',       // [2] ámbar
  '#a78bfa',       // [3] violeta
  '#2dd4bf',       // [4] teal
  '#f87171',       // [5] rojo
  '#fb923c',       // [6] naranja
  '#ec4899',       // [7] rosa/fucsia
  '#84cc16',       // [8] lima
  '#38bdf8',       // [9] azul cielo
] as const

// Acceso por nombre para los colores de gráficos menos comunes
export const CHART = {
  orange:  '#fb923c',
  pink:    '#ec4899',
  lime:    '#84cc16',
  sky:     '#38bdf8',
  teal:    '#2dd4bf',
} as const

export type ChartColorName = keyof typeof CHART

// Auditoria 2026-11 (#45): TASK_STATUS, TASK_PRIORITY, PROJECT_STATUS,
// TICKET_PRIORITY, TICKET_STATUS, RISK_LEVEL, SPACE, RADIUS, FONT y CARD_STYLE
// se exportaban y nadie los importaba (los estados viven en cada pantalla y las
// medidas en los tokens de index.css). Se retiran.

// ── Estilos de formulario reutilizables ──────────────────────────────────────
// Úsalos como: style={{ ...INPUT_STYLE, width: 200 }}
export const INPUT_STYLE: CSSProperties = {
  background:   'var(--surface-3)',
  border:       '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  padding:      '9px 13px',
  color:        'var(--text-1)',
  fontSize:     'var(--text-base)',
  outline:      'none',
  fontFamily:   'var(--font-sans)',
  width:        '100%',
  boxSizing:    'border-box',
}

export const LABEL_STYLE: CSSProperties = {
  fontSize:      'var(--text-xs)',
  fontWeight:    600,
  color:         'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display:       'block',
  marginBottom:  5,
}

// ── Helper: color semántico de un valor numérico ──────────────────────────────
export function budgetColor(pct: number): string {
  if (pct >= 100) return COLOR.danger
  if (pct >= 85)  return COLOR.warning
  return COLOR.success
}

export function marginColor(pct: number): string {
  if (pct < 0)  return COLOR.danger
  if (pct < 15) return COLOR.warning
  return COLOR.success
}
