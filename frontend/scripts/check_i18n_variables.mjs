// Las variables `{x}` de una clave son las mismas en los tres idiomas.
//
// ── Qué defecto caza, con los cuatro que encontró al escribirse ───────────────
//
// `t('clave', { total, active })` sustituye `{total}` y `{active}` en el texto
// del idioma activo. Si una traducción no lleva las mismas variables, pasa una
// de dos cosas, y ninguna avisa:
//
//   - **sobran en el texto**: el usuario lee `{count}` tal cual en pantalla;
//   - **faltan en el texto**: el dato simplemente no aparece, y la frase sigue
//     teniendo sentido — que es lo que hace que nadie lo reporte.
//
// Los cuatro casos reales que había, cada uno de un tipo distinto:
//
//   projects.subtitle          inglés y chino tenían una frase genérica SIN las
//                              tres cifras que el código pasa. La misma pantalla
//                              daba menos información según el idioma.
//   milestone_billing.subtitle el valor CASTELLANO decía «Team capacity
//                              projection — {weeks} weeks»: texto en inglés y de
//                              otro módulo.
//   m365.subtitle              igual: «{total} people · Reporting structure».
//   offline_indicator.pending_label
//                              `{count} pendiente{s}` esperaba que alguien
//                              pasara `s` valiendo "" o "s". Nadie la llama, así
//                              que habría mostrado «3 pendiente{s}».
//
// Los dos del medio son lo interesante: el descuadre de variables no era el
// defecto, era el síntoma que destapó dos valores copiados de otro módulo.
//
// Uso:  node scripts/check_i18n_variables.mjs
import es from '../src/i18n/langs/es.mjs'
import en from '../src/i18n/langs/en.mjs'
import zh from '../src/i18n/langs/zh.mjs'

function aplanar(obj, prefijo = '', salida = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const clave = prefijo ? `${prefijo}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) aplanar(v, clave, salida)
    else salida[clave] = v
  }
  return salida
}

/** Las variables del texto, ordenadas: el orden en la frase no importa. */
function variables(texto) {
  return [...String(texto).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
}

const BASE = aplanar(es)
const OTROS = { en: aplanar(en), zh: aplanar(zh) }

const descuadres = []
for (const [clave, valor] of Object.entries(BASE)) {
  if (typeof valor !== 'string') continue
  const esperadas = variables(valor)
  for (const [lang, dic] of Object.entries(OTROS)) {
    const traducido = dic[clave]
    if (traducido === undefined || typeof traducido !== 'string') continue
    const tiene = variables(traducido)
    if (tiene !== esperadas) {
      descuadres.push({ clave, lang, esperadas, tiene, valor, traducido })
    }
  }
}

if (descuadres.length === 0) {
  console.log(`✓ Las variables cuadran en las ${Object.keys(BASE).length} claves.`)
  process.exit(0)
}

console.error(`✗ ${descuadres.length} traducciones con variables que no cuadran.\n`)
console.error('  Una variable de más se lee tal cual en pantalla; una de menos hace')
console.error('  desaparecer el dato sin que la frase deje de tener sentido.\n')
for (const d of descuadres) {
  console.error(`  ${d.clave}  (${d.lang})`)
  console.error(`      es: {${d.esperadas || '—'}}  ${JSON.stringify(d.valor)}`)
  console.error(`      ${d.lang}: {${d.tiene || '—'}}  ${JSON.stringify(d.traducido)}`)
}
process.exit(1)
