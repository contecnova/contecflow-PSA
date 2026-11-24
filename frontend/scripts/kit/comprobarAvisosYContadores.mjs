// Comprobación de avisos de configuración y contadores (24-11-2026, paso 0 del programa de estabilidad
// de diseño). La usa scripts/kit_pendientes.mjs (sección `avisos` de kit-pendientes.json, cupo que solo baja).
//
// Dos reglas, contadas por fichero:
//   enlaceAConfiguracionAMano  un enlace a Configuración (`/settings/…` o una ruta antigua que redirige allí,
//                              `rutaAntigua` del catálogo) hecho a mano fuera de Configuración: `<Link to=…>`,
//                              `navigate(…)`, `href=…` o `to: …`. Desde fuera de Configuración se enlaza SIEMPRE con
//                              `AvisoDeConfiguracion` del kit (aviso + enlace solo a quien puede abrir la sección; sin
//                              permiso, «Pídeselo a tu administrador»), o con `rutaDeConfiguracion()` +
//                              `usePuedeConfigurar()` cuando el enlace es una tarjeta o un paso de una lista.
//                              No cuentan las redirecciones (`<Navigate … replace />` de rutas viejas).
//   contadorAMano              un contador de pendientes pintado a mano (el literal «99+»): se usa `BotonConContador`
//                              (botones de barra: campana, bandeja, chat…) o `Contador` (menús y listas) del kit.
import fs from 'node:fs'
import path from 'node:path'

export const COMPROBACIONES_AVISOS = ['enlaceAConfiguracionAMano', 'contadorAMano']

/** Donde enlazar a Configuración es lo normal (la propia Configuración, el menú, el buscador, las rutas). */
const PERMITIDOS_ENLACE = /^src\/(components\/ui\/|__tests__\/|pages\/settings-sections\/|pages\/settings\/|pages\/SettingsPage\.tsx$|App\.tsx$|components\/layout\/(menuLateral\.tsx|GlobalSearch\.tsx)$|services\/|i18n\/)|\.test\.tsx?$/
const PERMITIDOS_CONTADOR = /^src\/(components\/ui\/|__tests__\/|i18n\/)|\.test\.tsx?$/

function archivos(dir, salida = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) { if (e.name !== 'node_modules') archivos(p, salida) } else if (/\.tsx?$/.test(e.name)) salida.push(p)
  }
  return salida
}

/** Rutas antiguas que hoy redirigen a `/settings/<id>` (catálogo de Configuración). */
function rutasAntiguas(raiz) {
  const cat = path.join(raiz, 'src/pages/settings/catalogoDeAjustes.tsx')
  if (!fs.existsSync(cat)) return []
  return [...fs.readFileSync(cat, 'utf8').matchAll(/rutaAntigua:\s*'(\/[^']+)'/g)].map((m) => m[1])
}

export function recuentoAvisos(raiz) {
  const r = Object.fromEntries(COMPROBACIONES_AVISOS.map((c) => [c, {}]))
  const antiguas = rutasAntiguas(raiz).map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const destino = `/(?:settings${antiguas.length ? `|${antiguas.map((a) => a.slice(1)).join('|')}` : ''})(?=['"\`/?#])`
  const reEnlace = new RegExp(`(?:\\bto=\\{?\\s*|\\bto:\\s*|\\bnavigate\\(\\s*|\\bhref=\\{?\\s*)['"\`]${destino}`, 'g')
  const reContador = /(['"`])99\+\1/g
  for (const f of archivos(path.join(raiz, 'src'))) {
    const rel = path.relative(raiz, f).split(path.sep).join('/')
    const texto = fs.readFileSync(f, 'utf8')
    const suma = (regla) => { r[regla][rel] = (r[regla][rel] || 0) + 1 }
    if (!PERMITIDOS_ENLACE.test(rel)) {
      for (const m of texto.matchAll(reEnlace)) {
        // Las redirecciones de rutas viejas (`<Navigate to=… replace />`) no son enlaces que vea nadie.
        if (/<Navigate\s+$/.test(texto.slice(Math.max(0, m.index - 12), m.index))) continue
        suma('enlaceAConfiguracionAMano')
      }
    }
    if (!PERMITIDOS_CONTADOR.test(rel)) for (const _ of texto.matchAll(reContador)) suma('contadorAMano')
  }
  for (const c of COMPROBACIONES_AVISOS) r[c] = Object.fromEntries(Object.entries(r[c]).sort(([a], [b]) => a.localeCompare(b)))
  return r
}
