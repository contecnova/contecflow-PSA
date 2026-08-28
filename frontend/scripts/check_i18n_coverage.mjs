// Gate de cobertura de traducción (auditoría 2026-08, hallazgo 16).
//
// Antes había siete idiomas en el selector y ninguno completo: el usuario veía
// interfaz mezclada castellano-inglés en cualquiera que eligiese. Se retiraron
// los cuatro que no se venden (fr, de, pt, it) y pl, y quedan los tres que sí:
// castellano, inglés y chino.
//
// Este gate fija la cobertura MEDIDA de cada idioma como suelo: puede subir,
// nunca bajar. Sin él, añadir claves nuevas al castellano diluye silenciosamente
// la cobertura de los otros dos y se vuelve al punto de partida.
//
// Al traducir, subir los umbrales de COBERTURA_MINIMA — nunca bajarlos.
//
// Uso:
//   node scripts/check_i18n_coverage.mjs           # gate (sale 1 si baja)
//   node scripts/check_i18n_coverage.mjs --report  # sólo informe, sale 0
import { APP_LANGUAGES, APP_TRANSLATIONS } from '../src/i18n/appTranslations.mjs'

const BASE = 'es'

// Suelo medido el 2026-08-28. Subirlo conforme se traduzca.
const COBERTURA_MINIMA = {
  en: 62.0,
  zh: 62.0,
}

function aplanar(obj, prefijo = '', salida = new Set()) {
  for (const [k, v] of Object.entries(obj || {})) {
    const clave = prefijo ? `${prefijo}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) aplanar(v, clave, salida)
    else salida.add(clave)
  }
  return salida
}

const soloInforme = process.argv.includes('--report')
const clavesBase = aplanar(APP_TRANSLATIONS[BASE])
const codigos = APP_LANGUAGES.map((l) => l.code)

let fallos = 0

// El registro y los catálogos deben coincidir: un idioma en el selector sin
// catálogo cargado dejaría la interfaz en blanco al elegirlo.
const enRegistroSinCatalogo = codigos.filter((c) => !APP_TRANSLATIONS[c])
if (enRegistroSinCatalogo.length) {
  console.error(`✗ idiomas en APP_LANGUAGES sin catálogo: ${enRegistroSinCatalogo.join(', ')}`)
  fallos++
}
const conCatalogoSinRegistro = Object.keys(APP_TRANSLATIONS).filter((c) => !codigos.includes(c))
if (conCatalogoSinRegistro.length) {
  console.error(`✗ catálogos cargados que no están en APP_LANGUAGES: ${conCatalogoSinRegistro.join(', ')}`)
  fallos++
}

console.log(`Base (${BASE}): ${clavesBase.size} claves`)
for (const code of codigos) {
  if (code === BASE) {
    console.log(`  ${code}  100.0 %  (base)`)
    continue
  }
  const suyas = aplanar(APP_TRANSLATIONS[code] || {})
  const faltan = [...clavesBase].filter((k) => !suyas.has(k))
  const cobertura = ((clavesBase.size - faltan.length) / clavesBase.size) * 100
  const minimo = COBERTURA_MINIMA[code]

  const linea = `  ${code}  ${cobertura.toFixed(1).padStart(5)} %  (faltan ${faltan.length})`
  if (minimo === undefined) {
    console.log(`${linea}  — sin umbral definido`)
    continue
  }
  if (cobertura + 0.05 < minimo) {
    console.error(`${linea}  ✗ por debajo del suelo de ${minimo} %`)
    fallos++
  } else {
    console.log(`${linea}  ✓ suelo ${minimo} %`)
  }
}

if (fallos && !soloInforme) {
  console.error(
    '\nLa cobertura de traducción ha BAJADO. Suele pasar al añadir claves al ' +
      'castellano sin traducirlas: tradúcelas o retíralas.',
  )
  process.exit(1)
}
process.exit(0)
