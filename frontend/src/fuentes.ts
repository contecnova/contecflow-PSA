/**
 * Tipografías (19-11-2026).
 *
 * Auditoría de hardcodeados: `index.css` importaba las fuentes de Google Fonts
 * con una URL fija. Una instalación sin salida a internet (o que no quiere
 * llamar a Google: RGPD, la IP del usuario viaja a un tercero) no podía
 * evitarlo. Ahora la hoja de fuentes es configurable al compilar:
 *
 * - `VITE_FONTS_CSS_URL` sin definir → Google Fonts, como antes;
 * - `VITE_FONTS_CSS_URL=/fonts/fuentes.css` → servida desde el propio host;
 * - `VITE_FONTS_CSS_URL=` (vacía) → ninguna: se usan las de respaldo de
 *   `--font-*` en index.css (fuentes del sistema).
 *
 * Si cambia el origen, la CSP de `app/main.py` (style-src/font-src) debe
 * permitirlo.
 */
const GOOGLE_FONTS =
  'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Geist:wght@400;500;600;700;800&family=Geist+Mono:wght@400;500&display=swap'

export function cargarFuentes(): void {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {}
  const url = 'VITE_FONTS_CSS_URL' in env ? (env.VITE_FONTS_CSS_URL ?? '').trim() : GOOGLE_FONTS
  if (!url || typeof document === 'undefined') return
  if (document.querySelector(`link[data-fuentes]`)) return
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = url
  link.dataset.fuentes = '1'
  document.head.appendChild(link)
}
