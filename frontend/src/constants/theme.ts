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

// ── Estados de entidades ──────────────────────────────────────────────────────
export interface StatusToken {
  color: string
  label: string
}

export const TASK_STATUS: Record<string, StatusToken> = {
  todo:        { color: COLOR.text3,   label: 'Por hacer'    },
  in_progress: { color: COLOR.accent,  label: 'En progreso'  },
  review:      { color: COLOR.warning, label: 'Revisión'     },
  done:        { color: COLOR.success, label: 'Hecho'        },
  blocked:     { color: COLOR.danger,  label: 'Bloqueado'    },
  backlog:     { color: COLOR.surface4,label: 'Backlog'      },
  cancelled:   { color: COLOR.text4,   label: 'Cancelado'    },
}

export const TASK_PRIORITY: Record<string, StatusToken> = {
  low:      { color: COLOR.text2,   label: 'Baja'     },
  medium:   { color: COLOR.warning, label: 'Media'    },
  high:     { color: COLOR.danger,  label: 'Alta'     },
  critical: { color: COLOR.danger,  label: 'Crítica'  },
}

export const PROJECT_STATUS: Record<string, StatusToken> = {
  planning:  { color: COLOR.text2,   label: 'Planificación' },
  active:    { color: COLOR.accent,  label: 'Activo'        },
  on_hold:   { color: COLOR.warning, label: 'En espera'     },
  paused:    { color: COLOR.warning, label: 'Pausado'       },
  completed: { color: COLOR.success, label: 'Completado'    },
  closed:    { color: COLOR.success, label: 'Cerrado'       },
  cancelled: { color: COLOR.text3,   label: 'Cancelado'     },
  archived:  { color: COLOR.text3,   label: 'Archivado'     },
  at_risk:   { color: COLOR.danger,  label: 'En riesgo'     },
}

export const TICKET_PRIORITY: Record<string, StatusToken> = {
  p1_critical: { color: COLOR.danger,  label: 'P1 Crítico' },
  p2_high:     { color: COLOR.orange,  label: 'P2 Alto'    },
  p3_medium:   { color: COLOR.warning, label: 'P3 Medio'   },
  p4_low:      { color: COLOR.text2,   label: 'P4 Bajo'    },
}

export const TICKET_STATUS: Record<string, StatusToken> = {
  new:            { color: COLOR.accent,  label: 'Nuevo'        },
  assigned:       { color: COLOR.accent,  label: 'Asignado'     },
  in_progress:    { color: COLOR.accent,  label: 'En progreso'  },
  pending_client: { color: COLOR.warning, label: 'Pend. cliente'},
  resolved:       { color: COLOR.success, label: 'Resuelto'     },
  closed:         { color: COLOR.success, label: 'Cerrado'      },
  cancelled:      { color: COLOR.text3,   label: 'Cancelado'    },
}

export const RISK_LEVEL: Record<string, StatusToken> = {
  low:      { color: COLOR.success, label: 'Bajo'    },
  medium:   { color: COLOR.warning, label: 'Medio'   },
  high:     { color: COLOR.danger,  label: 'Alto'    },
  critical: { color: COLOR.danger,  label: 'Crítico' },
}

// ── Espaciado (px, múltiplos de 4) ────────────────────────────────────────────
export const SPACE = { xs:4, sm:8, md:12, lg:16, xl:24, xxl:32, xxxl:48 } as const

// ── Radios de borde ───────────────────────────────────────────────────────────
export const RADIUS = { sm:6, md:10, lg:14, xl:18, full:9999 } as const

// ── Tipografía ────────────────────────────────────────────────────────────────
export const FONT = {
  sans: "'DM Sans', system-ui, sans-serif",
  mono: "'Geist Mono', 'Space Mono', monospace",
  size: { xs:10, sm:11, base:13, md:14, lg:16, xl:20, xxl:24 },
} as const

// ── Estilos de formulario reutilizables ──────────────────────────────────────
// Úsalos como: style={{ ...INPUT_STYLE, width: 200 }}
export const INPUT_STYLE: CSSProperties = {
  background:   'var(--surface-3)',
  border:       '1px solid var(--surface-4)',
  borderRadius: RADIUS.md,
  padding:      '9px 13px',
  color:        'var(--text-1)',
  fontSize:     FONT.size.base,
  outline:      'none',
  fontFamily:   'var(--font-sans)',
  width:        '100%',
  boxSizing:    'border-box',
}

export const LABEL_STYLE: CSSProperties = {
  fontSize:      FONT.size.sm,
  fontWeight:    600,
  color:         'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display:       'block',
  marginBottom:  5,
}

export const CARD_STYLE: CSSProperties = {
  background:   'var(--surface-2)',
  border:       '1px solid var(--surface-4)',
  borderRadius: RADIUS.lg,
  padding:      SPACE.xl,
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
