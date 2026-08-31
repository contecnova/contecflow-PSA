// Gate: ningún fichero de idioma puede declarar la misma clave dos veces.
//
// Auditoría 2026-08 (hallazgo 16). Encontrado al intentar cerrar la traducción:
// `en.mjs` contiene `client_portal.additional_projects_access` en la línea 119,
// con su texto en inglés perfectamente traducido — y el módulo cargado NO la
// tiene. La causa es que la clave del namespace está declarada dos veces en el
// mismo objeto, y en JavaScript **la última gana en silencio**: todas las
// traducciones de la primera declaración se descartan al cargar.
//
// Es el peor tipo de fallo de este fichero: el trabajo está hecho, está en el
// repositorio, se puede leer, y no llega al usuario. Nada avisa — ni el linter,
// ni el gate de cobertura, que compara el objeto YA COLAPSADO.
//
// Este gate lee el fichero como TEXTO y sigue las llaves, que es la única forma
// de ver las dos declaraciones: cualquier análisis sobre el objeto cargado ve una
// sola.
//
// Uso:
//   node scripts/check_i18n_duplicates.mjs            # gate (sale 1 si hay)
//   node scripts/check_i18n_duplicates.mjs --report   # informe, sale 0
import { readFileSync } from 'node:fs'

import { APP_LANGUAGES } from '../src/i18n/appTranslations.mjs'

const soloInforme = process.argv.includes('--report')

/**
 * Claves declaradas en un fichero de idioma, con su ruta de anidamiento real.
 *
 * Se sigue el balance de llaves línea a línea en lugar de fiarse de la
 * indentación: en estos ficheros la indentación NO es fiable — hay namespaces a
 * 2 espacios y otros a 4 en el mismo objeto, que es justo lo que hizo invisible
 * el duplicado.
 */
function clavesDeclaradas(ruta) {
  const lineas = readFileSync(ruta, 'utf8').split('\n')
  const pila = [] // ruta de claves de los objetos abiertos
  const declaradas = [] // { ruta, linea }

  for (let i = 0; i < lineas.length; i++) {
    const linea = lineas[i]
    // Se ignoran los comentarios de línea completa.
    if (linea.trim().startsWith('//')) continue

    const abre = linea.match(/^\s*([A-Za-z0-9_]+)\s*:\s*\{\s*$/)
    if (abre) {
      declaradas.push({ ruta: [...pila, abre[1]].join('.'), linea: i + 1, esObjeto: true })
      pila.push(abre[1])
      continue
    }

    const hoja = linea.match(/^\s*([A-Za-z0-9_]+)\s*:\s*(['"`])/)
    if (hoja) {
      declaradas.push({ ruta: [...pila, hoja[1]].join('.'), linea: i + 1, esObjeto: false })
      continue
    }

    // Cierre de objeto: `},` o `}` a solas.
    if (/^\s*\}\s*,?\s*;?\s*$/.test(linea) && pila.length) pila.pop()
  }
  return declaradas
}

let fallos = 0
let totalDup = 0

for (const { code } of APP_LANGUAGES) {
  const ruta = `src/i18n/langs/${code}.mjs`
  let declaradas
  try {
    declaradas = clavesDeclaradas(ruta)
  } catch {
    console.error(`✗ no se pudo leer ${ruta}`)
    fallos++
    continue
  }

  const porRuta = new Map()
  for (const d of declaradas) {
    if (!porRuta.has(d.ruta)) porRuta.set(d.ruta, [])
    porRuta.get(d.ruta).push(d)
  }

  const duplicadas = [...porRuta.entries()].filter(([, apariciones]) => apariciones.length > 1)

  console.log(`${code}: ${declaradas.length} claves declaradas, ${duplicadas.length} duplicadas`)

  if (!duplicadas.length) continue

  fallos++
  // Se ordenan por cuántas traducciones se pierden: el duplicado de un namespace
  // entero se lleva por delante todo su contenido.
  const conCoste = duplicadas
    .map(([ruta, apariciones]) => {
      // Las claves que caen dentro de cada declaración perdida.
      const perdidas = apariciones.slice(0, -1).reduce((n, ap) => {
        if (!ap.esObjeto) return n + 1
        const dentro = declaradas.filter(
          (d) => d.ruta.startsWith(`${ruta}.`) && d.linea > ap.linea,
        )
        // Sólo las que están antes de la siguiente declaración de la misma ruta.
        const siguiente = apariciones.find((a) => a.linea > ap.linea)
        return n + dentro.filter((d) => !siguiente || d.linea < siguiente.linea).length
      }, 0)
      return { ruta, apariciones, perdidas }
    })
    .sort((a, b) => b.perdidas - a.perdidas)

  for (const { ruta, apariciones, perdidas } of conCoste) {
    totalDup += perdidas
    const lineasTxt = apariciones.map((a) => a.linea).join(', ')
    console.error(
      `  ✗ ${ruta} declarada ${apariciones.length} veces (líneas ${lineasTxt})` +
        (perdidas ? ` — se descartan ${perdidas} traducciones` : ''),
    )
  }
}

if (!fallos) {
  console.log('\n✓ ningún fichero de idioma declara la misma clave dos veces')
  process.exit(0)
}

console.error(
  `\nEn JavaScript la ÚLTIMA declaración gana, así que esas traducciones están en\n` +
    `el repositorio y no llegan al usuario. Total descartado: ${totalDup} traducciones.\n` +
    'Se arregla fusionando las declaraciones duplicadas en una sola.',
)
process.exit(soloInforme ? 0 : 1)
