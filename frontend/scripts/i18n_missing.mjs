// Extrae las claves que le faltan a un idioma, con su texto en castellano.
//
// Auditoría 2026-08 (hallazgo 16). Inglés y chino estaban al 62,2 %: 1.419 claves
// cada uno. Traducirlas exige saber exactamente cuáles y qué dicen, agrupadas por
// namespace para poder trabajarlas en lotes revisables y con contexto — una
// etiqueta suelta no se traduce bien sin saber de qué pantalla es.
//
// Uso:
//   node scripts/i18n_missing.mjs en                    # informe por namespace
//   node scripts/i18n_missing.mjs en --ns alm           # sólo ese namespace
//   node scripts/i18n_missing.mjs en --ns alm --json    # JSON para traducir
//   node scripts/i18n_missing.mjs en --json > todo.json # todas, en JSON
import { APP_TRANSLATIONS } from '../src/i18n/appTranslations.mjs'

const BASE = 'es'

function aplanar(obj, prefijo = '', salida = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const clave = prefijo ? `${prefijo}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) aplanar(v, clave, salida)
    else salida[clave] = v
  }
  return salida
}

const args = process.argv.slice(2)
const idioma = args.find((a) => !a.startsWith('--'))
if (!idioma) {
  console.error('Uso: node scripts/i18n_missing.mjs <idioma> [--ns <namespace>] [--json]')
  process.exit(1)
}
if (!APP_TRANSLATIONS[idioma]) {
  console.error(`Idioma desconocido: ${idioma}. Disponibles: ${Object.keys(APP_TRANSLATIONS)}`)
  process.exit(1)
}

const nsPedido = args.includes('--ns') ? args[args.indexOf('--ns') + 1] : null
const comoJson = args.includes('--json')

const base = aplanar(APP_TRANSLATIONS[BASE])
const suyas = aplanar(APP_TRANSLATIONS[idioma])

let faltan = Object.keys(base).filter((k) => !(k in suyas))
if (nsPedido) faltan = faltan.filter((k) => k.split('.')[0] === nsPedido)

if (comoJson) {
  // El texto castellano es lo que hay que traducir; la clave es la identidad.
  const salida = {}
  for (const k of faltan.sort()) salida[k] = base[k]
  console.log(JSON.stringify(salida, null, 1))
  process.exit(0)
}

const porNs = {}
for (const k of faltan) {
  const ns = k.split('.')[0]
  ;(porNs[ns] ??= []).push(k)
}

console.log(`${idioma}: faltan ${faltan.length} claves en ${Object.keys(porNs).length} namespaces`)
if (nsPedido) {
  for (const k of faltan.sort()) console.log(`  ${k}\n      ${JSON.stringify(base[k])}`)
} else {
  for (const [ns, ks] of Object.entries(porNs).sort((a, b) => b[1].length - a[1].length)) {
    console.log(`  ${String(ks.length).padStart(5)}  ${ns}`)
  }
}
