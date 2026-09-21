// Mete un modulo nuevo de claves en los tres ficheros de idioma.
//
// Los diccionarios son objetos anidados por modulo —`es.mjs`, `en.mjs`,
// `zh.mjs`, ~4.000 lineas cada uno— y `t('modulo.clave')` parte por el primer
// punto. Insertar a mano en tres sitios es como se llega a lo que encontro el
// gate de duplicados: un modulo declarado dos veces, donde JavaScript se queda
// con el ultimo y descarta en silencio las traducciones del primero.
//
// Esto lo hace de una vez y falla si el modulo ya existe en alguno de los tres.
//
// Uso:  node scripts/i18n_insertar_modulo.mjs <fichero.json>
//
// El JSON: { "modulo": "portalusers", "es": {...}, "en": {...}, "zh": {...} }
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const LANGS = join(RAIZ, 'src', 'i18n', 'langs')

const plan = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const modulo = plan.modulo

function comoLiteral(valor) {
  // Comillas simples, que es el estilo del fichero, escapando las de dentro.
  return `'${valor.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`
}

for (const lang of ['es', 'en', 'zh']) {
  const ruta = join(LANGS, `${lang}.mjs`)
  const texto = readFileSync(ruta, 'utf8')

  const entradas = plan[lang]
  const faltan = Object.keys(plan.es).filter((k) => !(k in entradas))
  if (faltan.length) {
    console.error(`✗ ${lang} no traduce: ${faltan.join(', ')}. Nada tocado.`)
    process.exit(1)
  }

  const lineas = texto.split('\n')
  const cuerpo = Object.entries(entradas)
    .map(([k, v]) => `    ${/^[A-Za-z_$][\w$]*$/.test(k) ? k : `'${k}'`}: ${comoLiteral(v)},`)

  // El modulo casi siempre EXISTE ya: `subcontractors`, `okrs`, `changes` y
  // `sprints` tenian su namespace desde antes, con las claves que alguien fue
  // extrayendo a mano. Crear un segundo bloque con el mismo nombre es
  // exactamente el defecto que encontro el gate de duplicados —JavaScript se
  // queda con el ultimo y descarta el primero en silencio—, asi que si existe
  // se FUSIONA dentro, y si no, se crea al final.
  const apertura = lineas.findIndex((l) => new RegExp(`^  ${modulo}:\\s*\\{`).test(l))

  if (apertura >= 0) {
    // El cierre del modulo: la primera linea `  },` a su misma indentacion.
    const cierreMod = lineas.findIndex((l, i) => i > apertura && /^  \},?$/.test(l.trimEnd()))
    if (cierreMod < 0) {
      console.error(`✗ no se encuentra el cierre del modulo '${modulo}' en ${lang}.mjs`)
      process.exit(1)
    }
    const dentro = lineas.slice(apertura + 1, cierreMod).join('\n')
    const repes = Object.keys(entradas)
      .filter((k) => new RegExp(`^\\s{4}'?${k}'?:`, 'm').test(dentro))
    if (repes.length) {
      console.error(
        `✗ ${lang}.mjs: '${modulo}' ya tiene ${repes.join(', ')}. Nada tocado.\n` +
        '  Reutiliza la clave existente en vez de duplicar el texto.',
      )
      process.exit(1)
    }
    // La ultima entrada del modulo puede no llevar coma final —varios modulos
    // de `en.mjs` acaban asi—, y sin ella lo insertado es un error de sintaxis
    // que tumba el fichero entero: `Unexpected identifier`. Se pone antes de
    // empalmar.
    const previa = cierreMod - 1
    if (previa > apertura && !/[,{]\s*$/.test(lineas[previa])) {
      lineas[previa] = `${lineas[previa].trimEnd()},`
    }
    lineas.splice(cierreMod, 0, ...cuerpo)
  } else {
    // Antes del cierre del objeto: la ultima linea que lo cierra al margen
    // izquierdo. Los tres ficheros acaban en `};` y luego `export default`,
    // asi que se aceptan las dos formas.
    const cierre = lineas.reduce(
      (acc, l, i) => (l.trimEnd() === '}' || l.trimEnd() === '};' ? i : acc), -1,
    )
    if (cierre < 0) {
      console.error(`✗ no se encuentra el cierre del objeto en ${lang}.mjs`)
      process.exit(1)
    }
    lineas.splice(cierre, 0, `  ${modulo}: {`, ...cuerpo, '  },')
  }

  writeFileSync(ruta, lineas.join('\n'), 'utf8')
  console.log(
    `✓ ${lang}.mjs  +${Object.keys(entradas).length} claves ` +
    `${apertura >= 0 ? 'fusionadas en' : 'en modulo nuevo'} '${modulo}'`,
  )
}
