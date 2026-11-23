/**
 * Tipografías servidas desde el propio host (23-11-2026).
 *
 * Antes (19-11-2026) la hoja de fuentes venía de Google Fonts salvo que se
 * definiera `VITE_FONTS_CSS_URL`. Cada visita mandaba la IP del navegador a
 * Google (RGPD: transferencia a un tercero sin base legal; auditoría
 * 2026-11-22, informe 05 A.7). Ahora las familias se empaquetan con la app
 * desde los paquetes `@fontsource/*` (ficheros .woff2 con `unicode-range`:
 * el navegador solo descarga los subconjuntos que pinta) y Vite las sirve
 * como recursos propios. La CSP (`app/main.py`, `frontend/nginx.frontend.conf`,
 * `vite.config.js`) ya no permite `fonts.googleapis.com` ni `fonts.gstatic.com`.
 *
 * Mismas familias y pesos que la URL de Google de antes:
 * - DM Sans 400-800 y Geist 400-800 (`--font-sans`);
 * - Geist Mono 400-500 (`--font-mono`).
 * El chino (CJK) no lo cubrían ni Google ni estas familias: sigue cayendo a
 * la fuente del sistema de la pila `--font-sans` (`system-ui`), igual que antes.
 */
import '@fontsource/dm-sans/400.css'
import '@fontsource/dm-sans/500.css'
import '@fontsource/dm-sans/600.css'
import '@fontsource/dm-sans/700.css'
import '@fontsource/dm-sans/800.css'
import '@fontsource/geist/400.css'
import '@fontsource/geist/500.css'
import '@fontsource/geist/600.css'
import '@fontsource/geist/700.css'
import '@fontsource/geist/800.css'
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
