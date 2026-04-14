/**
 * theme.js — Design tokens centralizados de Clarive
 *
 * REGLA: Nunca uses colores hex directamente en componentes.
 * - En CSS/JSX inline: usa var(--accent), var(--surface-2), etc.
 * - En Recharts/Chart.js/SVG/Canvas (donde CSS vars no funcionan):
 *   importa COLOR, CHART_COLORS desde aquí.
 *
 * Las CSS vars están definidas en src/index.css
 */

// ── Helper: leer CSS var en runtime (para Recharts donde CSS vars no aplican) ──
/**
 * getAccent() — Lee --accent del DOM en tiempo real.
 * Úsalo en componentes que se re-renderizan cuando cambia el tema.
 * Ejemplo en Recharts: stroke={getAccent()}
 */
export function getAccent() {
  if (typeof window === 'undefined') return '#4f8ef7'
  return getComputedStyle(document.documentElement)
    .getPropertyValue('--accent').trim() || '#4f8ef7'
}

export function getCSSVar(varName, fallback = '') {
  if (typeof window === 'undefined') return fallback
  return getComputedStyle(document.documentElement)
    .getPropertyValue(varName).trim() || fallback
}

// ── Colores del sistema ────────────────────────────────────────────────────────
export const COLOR = {
  // Superficies (de más oscuro a más claro)
  surface0:    '#080c14',
  surface1:    '#0d1220',
  surface2:    '#111827',
  surface3:    '#172133',
  surface4:    '#1e2d45',
  surface5:    '#253550',

  // Jerarquía de texto
  text1:       '#f0f4ff',   // headings, valores clave
  text2:       '#8899bb',   // labels, descripciones
  text3:       '#4a5a78',   // placeholders, disabled
  text4:       '#2a3a54',   // muy sutil

  // Accent (azul índigo)
  accent:      '#4f8ef7',
  accentDim:   '#2d5fd4',
  accentGlow:  'rgba(79,142,247,0.15)',
  accentMuted: 'rgba(79,142,247,0.08)',

  // Semánticos
  success:       '#34d399',
  successBg:     'rgba(52,211,153,0.08)',
  successBorder: 'rgba(52,211,153,0.20)',
  warning:       '#f59e0b',
  warningBg:     'rgba(245,158,11,0.08)',
  warningBorder: 'rgba(245,158,11,0.20)',
  danger:        '#f87171',
  dangerBg:      'rgba(248,113,113,0.08)',
  dangerBorder:  'rgba(248,113,113,0.20)',
  info:          '#60a5fa',
  infoBg:        'rgba(96,165,250,0.08)',

  // Purple — AI / features premium
  purple:    '#a78bfa',
  purpleBg:  'rgba(167,139,250,0.08)',

  // Overlays
  overlay:      'rgba(8,12,20,0.85)',
  overlayLight: 'rgba(8,12,20,0.60)',
}

// ── Paleta secuencial para gráficos ───────────────────────────────────────────
// Usar en Recharts, Chart.js, D3, SVG donde CSS vars no aplican
// ── Paleta extendida para gráficos con más series ────────────────────────────
// Usar en orden: para 8+ series en Recharts, CumulativeFlow, etc.
export const CHART_COLORS_EXTENDED = [
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
]

export const CHART_COLORS = [
  COLOR.accent,    // [0] azul índigo
  COLOR.success,   // [1] verde esmeralda
  COLOR.warning,   // [2] ámbar
  COLOR.purple,    // [3] violeta
  '#2dd4bf',       // [4] teal
  COLOR.danger,    // [5] rojo
  '#fb923c',       // [6] naranja
  '#ec4899',       // [7] rosa/fucsia
  '#84cc16',       // [8] lima
  '#38bdf8',       // [9] azul cielo
]

// Acceso por nombre para los colores de gráficos menos comunes
export const CHART = {
  orange:  '#fb923c',
  pink:    '#ec4899',
  lime:    '#84cc16',
  sky:     '#38bdf8',
  teal:    '#2dd4bf',
}

// ── Estados de entidades ──────────────────────────────────────────────────────
export const TASK_STATUS = {
  todo:        { color: COLOR.text3,   label: 'Por hacer'    },
  in_progress: { color: COLOR.accent,  label: 'En progreso'  },
  review:      { color: COLOR.warning, label: 'Revisión'     },
  done:        { color: COLOR.success, label: 'Hecho'        },
  blocked:     { color: COLOR.danger,  label: 'Bloqueado'    },
  backlog:     { color: COLOR.surface4,label: 'Backlog'      },
  cancelled:   { color: COLOR.text4,   label: 'Cancelado'    },
}

export const TASK_PRIORITY = {
  low:      { color: COLOR.text2,   label: 'Baja'     },
  medium:   { color: COLOR.warning, label: 'Media'    },
  high:     { color: COLOR.danger,  label: 'Alta'     },
  critical: { color: COLOR.danger,  label: 'Crítica'  },
}

export const PROJECT_STATUS = {
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

export const TICKET_PRIORITY = {
  p1_critical: { color: COLOR.danger,  label: 'P1 Crítico' },
  p2_high:     { color: COLOR.danger,  label: 'P2 Alto'    },
  p3_medium:   { color: COLOR.warning, label: 'P3 Medio'   },
  p4_low:      { color: COLOR.text2,   label: 'P4 Bajo'    },
}

export const TICKET_STATUS = {
  new:            { color: COLOR.accent,  label: 'Nuevo'        },
  assigned:       { color: COLOR.accent,  label: 'Asignado'     },
  in_progress:    { color: COLOR.accent,  label: 'En progreso'  },
  pending_client: { color: COLOR.warning, label: 'Pend. cliente'},
  resolved:       { color: COLOR.success, label: 'Resuelto'     },
  closed:         { color: COLOR.success, label: 'Cerrado'      },
  cancelled:      { color: COLOR.text3,   label: 'Cancelado'    },
}

export const RISK_LEVEL = {
  low:      { color: COLOR.success, label: 'Bajo'    },
  medium:   { color: COLOR.warning, label: 'Medio'   },
  high:     { color: COLOR.danger,  label: 'Alto'    },
  critical: { color: COLOR.danger,  label: 'Crítico' },
}

// ── Espaciado (px, múltiplos de 4) ────────────────────────────────────────────
export const SPACE = { xs:4, sm:8, md:12, lg:16, xl:24, xxl:32, xxxl:48 }

// ── Radios de borde ───────────────────────────────────────────────────────────
export const RADIUS = { sm:6, md:10, lg:14, xl:18, full:9999 }

// ── Tipografía ────────────────────────────────────────────────────────────────
export const FONT = {
  sans: "'DM Sans', system-ui, sans-serif",
  mono: "'Geist Mono', 'Space Mono', monospace",
  size: { xs:10, sm:11, base:13, md:14, lg:16, xl:20, xxl:24 },
}

// ── Estilos de formulario reutilizables ──────────────────────────────────────
// Úsalos como: style={{ ...INPUT_STYLE, width: 200 }}
export const INPUT_STYLE = {
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

export const LABEL_STYLE = {
  fontSize:      FONT.size.sm,
  fontWeight:    600,
  color:         'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display:       'block',
  marginBottom:  5,
}

export const CARD_STYLE = {
  background:   'var(--surface-2)',
  border:       '1px solid var(--surface-4)',
  borderRadius: RADIUS.lg,
  padding:      SPACE.xl,
}

// ── Helper: color semántico de un valor numérico ──────────────────────────────
export function budgetColor(pct) {
  if (pct >= 100) return COLOR.danger
  if (pct >= 85)  return COLOR.warning
  return COLOR.success
}

export function marginColor(pct) {
  if (pct < 0)  return COLOR.danger
  if (pct < 15) return COLOR.warning
  return COLOR.success
}
