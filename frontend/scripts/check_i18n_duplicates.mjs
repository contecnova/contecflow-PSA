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
import ts from 'typescript'

import { APP_LANGUAGES } from '../src/i18n/appTranslations.mjs'

const soloInforme = process.argv.includes('--report')

/**
 * Claves declaradas en un fichero de idioma, con su ruta de anidamiento real.
 *
 * Se lee el AST (parser de TypeScript) en lugar de seguir las líneas: en estos
 * ficheros hay líneas con varias claves (`a: 'x', b: 'y'`) y namespaces con
 * sangrías distintas, y un análisis por líneas se deja duplicados sin ver
 * (Segunda auditoría 2026-11: `service_desk.type_change` y otras 7 claves del
 * castellano, que el gate anterior daba por limpias).
 */
function clavesDeclaradas(ruta) {
  const fuente = readFileSync(ruta, 'utf8')
  const sf = ts.createSourceFile(ruta, fuente, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
  const declaradas = [] // { ruta, linea, esObjeto }

  const visitar = (nodo, camino) => {
    if (ts.isObjectLiteralExpression(nodo)) {
      for (const p of nodo.properties) {
        if (!ts.isPropertyAssignment(p) || !(ts.isIdentifier(p.name) || ts.isStringLiteral(p.name))) continue
        const completa = camino ? `${camino}.${p.name.text}` : p.name.text
        const { line } = sf.getLineAndCharacterOfPosition(p.getStart())
        declaradas.push({ ruta: completa, linea: line + 1, esObjeto: ts.isObjectLiteralExpression(p.initializer) })
        visitar(p.initializer, completa)
      }
      return
    }
    ts.forEachChild(nodo, (h) => visitar(h, camino))
  }
  visitar(sf, '')
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
