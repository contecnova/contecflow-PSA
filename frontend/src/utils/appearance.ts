/**
 * appearance.ts — Aplica al DOM el acento y la densidad del perfil.
 * Un solo sitio: lo llaman useUserPreferences (al cargar y al guardar) y el
 * panel de perfil (vista previa). Los valores viven en index.css.
 */
import { alpha } from '../constants/theme'

const HEX6 = /^#[0-9a-fA-F]{6}$/

/** Luminancia relativa WCAG 2.x de un #rrggbb. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/**
 * Texto sobre un acento elegido por el usuario: el extremo (blanco o negro)
 * que más contrasta. Con los dos extremos el peor caso es 4,58:1, así que
 * cumple AA con cualquier color.
 */
export function onAccentFor(hex: string): string {
  const l = luminance(hex)
  return (1.05 / (l + 0.05)) >= ((l + 0.05) / 0.05) ? 'var(--on-accent-light)' : 'var(--on-accent-dark)'
}

export function applyAccent(color: string | null | undefined): void {
  const root = document.documentElement
  if (!color || !HEX6.test(color)) {
    // Sin acento propio: manda el del tema, con su --on-accent
    for (const v of ['--accent', '--accent-muted', '--accent-glow', '--on-accent']) root.style.removeProperty(v)
    return
  }
  root.style.setProperty('--accent', color)
  root.style.setProperty('--accent-muted', alpha(color, '14'))
  root.style.setProperty('--accent-glow', alpha(color, '26'))
  root.style.setProperty('--on-accent', onAccentFor(color))
}

/** La densidad sólo escribe el atributo; los tokens que cambia están en index.css. */
export function applyDensity(density: string | null | undefined): void {
  document.documentElement.setAttribute('data-density', density || 'normal')
}
