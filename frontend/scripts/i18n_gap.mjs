// Mide las claves que le faltan a cada idioma respecto al castellano (base).
//
// Auditoría 2026-08 (hallazgo 16). `check_i18n.mjs` daba un total agregado;
// esto lo desglosa por idioma para poder decidir qué idiomas se mantienen y qué
// falta exactamente en cada uno.
//
// Uso: node scripts/i18n_gap.mjs [--keys en]
import { APP_TRANSLATIONS } from '../src/i18n/appTranslations.mjs'

const BASE = 'es'

function aplanar(obj, prefijo = '', salida = new Set()) {
  for (const [k, v] of Object.entries(obj || {})) {
    const clave = prefijo ? `${prefijo}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) aplanar(v, clave, salida)
    else salida.add(clave)
  }
  return salida
}

const clavesBase = aplanar(APP_TRANSLATIONS[BASE])
const idiomas = Object.keys(APP_TRANSLATIONS).filter((l) => l !== BASE)

const detalle = process.argv.includes('--keys')
  ? process.argv[process.argv.indexOf('--keys') + 1]
  : null

console.log(`claves en ${BASE}: ${clavesBase.size}`)
for (const lang of idiomas) {
  const suyas = aplanar(APP_TRANSLATIONS[lang])
  const faltan = [...clavesBase].filter((k) => !suyas.has(k))
  const sobran = [...suyas].filter((k) => !clavesBase.has(k))
  const cobertura = (((clavesBase.size - faltan.length) / clavesBase.size) * 100).toFixed(1)
  console.log(
    `  ${lang.padEnd(3)} ${String(suyas.size).padStart(5)} claves | ` +
      `faltan ${String(faltan.length).padStart(5)} | sobran ${String(sobran.length).padStart(4)} | ` +
      `cobertura ${cobertura}%`,
  )
  if (detalle === lang) {
    console.log('\n  claves que faltan en ' + lang + ':')
    for (const k of faltan) console.log('    ' + k)
  }
}
