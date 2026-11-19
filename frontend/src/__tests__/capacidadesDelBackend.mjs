/**
 * Ayuda de pruebas (19-11-2026, matriz de permisos): las capacidades por rol
 * leídas del catálogo del backend (`app/core/capacidades.py`), para que los
 * tests simulen un rol sin copiar listas de roles.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const aqui = dirname(fileURLToPath(import.meta.url))
const fuente = readFileSync(resolve(aqui, '../../../app/core/capacidades.py'), 'utf8')

const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor']

/** Constantes de roles del módulo (`INTERNOS = (...)`, `TODOS = ROLES`, `NADIE = ()`). */
function constantes() {
  /** @type {Record<string, string[]>} */
  const res = { ROLES, TODOS: ROLES }
  for (const m of fuente.matchAll(/^([A-Z_]+)(?::[^=\n]*)? = \(([^)]*)\)/gm)) {
    res[m[1]] = [...m[2].matchAll(/"([a-z_]+)"/g)].map(x => x[1])
  }
  return res
}

/** nombre de capacidad → roles por defecto. @type {Record<string, string[]>} */
export const CATALOGO_DEL_BACKEND = (() => {
  const k = constantes()
  /** @type {Record<string, string[]>} */
  const res = {}
  for (const m of fuente.matchAll(/^\s+"([a-z_]+\.[a-z_]+)": _c\(\s*(\([^)]*\)|[A-Z_]+)/gm)) {
    res[m[1]] = m[2].startsWith('(') ? [...m[2].matchAll(/"([a-z_]+)"/g)].map(x => x[1]) : k[m[2]]
  }
  return res
})()

/** Capacidades por defecto de un rol base (superadmin: todas). */
export function capacidadesDe(rol, esSuperadmin = false) {
  return Object.entries(CATALOGO_DEL_BACKEND)
    .filter(([, roles]) => esSuperadmin || roles.includes(rol))
    .map(([n]) => n)
    .sort()
}

/** `puede` de un usuario de prueba con ese rol. */
export const puedeComo = (rol, esSuperadmin = false) => {
  const caps = new Set(capacidadesDe(rol, esSuperadmin))
  return c => caps.has(c)
}
