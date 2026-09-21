// Saca el texto castellano del JSX y lo deja pasando por `t()`.
//
// Es la herramienta para bajar lo que mide `check_i18n_literales.mjs`. Edita el
// codigo por posiciones exactas del AST de TypeScript, de atras hacia delante
// para que los desplazamientos no se muevan, y escribe aparte las claves nuevas
// en castellano. Las traducciones a ingles y chino NO las inventa: se escriben
// a mano en `en.mjs` y `zh.mjs`, que es trabajo de idioma, no de refactor.
//
// Uso:
//   node scripts/i18n_extraer_literales.mjs --plan  src/pages/X.tsx
//   node scripts/i18n_extraer_literales.mjs --aplicar src/pages/X.tsx
//
// `--plan` no toca nada: imprime que clave le pondria a cada literal, para
// poder revisarlo antes. `--aplicar` edita el fichero y vuelca a stdout el
// bloque de claves castellanas listo para pegar.
//
// ── Donde inserta el hook, y por que ahi ──────────────────────────────────────
//
// `t` sale de `useAppLang()`, que es un hook de React: solo puede llamarse en el
// cuerpo del componente. El literal, en cambio, suele estar dentro de un
// `.map(...)` o de un `renderX` anidado. Si el hook se insertara en la funcion
// que envuelve al literal, quedaria dentro del callback — ilegal, y de las que
// funcionan hasta que la lista se queda vacia.
//
// Por eso se busca la funcion de PRIMER NIVEL del modulo que contiene el
// literal, que es el componente, y ahi va el hook.
import { readFileSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'
import ts from 'typescript'

const ATRIBUTOS_VISIBLES = new Set([
  'placeholder', 'title', 'label', 'aria-label', 'alt', 'aria-placeholder',
])

const CASTELLANO = new RegExp(
  '[áéíóúñÁÉÍÓÚÑ¿¡]|\\b(de|la|el|los|las|del|para|con|sin|por|que|una|un|se|su|al|no|mas|este|esta|hay|son|como|cuando|todos|todas|nuevo|nueva)\\b',
  'i',
)

function sinAcentos(s) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '')
}

function aClave(texto) {
  return sinAcentos(texto)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .split('_').filter(Boolean).slice(0, 7).join('_') || 'texto'
}

function espacioDeNombres(ruta) {
  return aClave(basename(ruta).replace(/\.tsx$/, '').replace(/Page|Sections|Tab/g, ''))
}

/** Las funciones de primer nivel del modulo, con su rango. */
function componentesDePrimerNivel(fuente) {
  const salida = []
  for (const sentencia of fuente.statements) {
    if (ts.isFunctionDeclaration(sentencia) && sentencia.body) {
      salida.push({ nombre: sentencia.name?.getText(fuente) ?? '?', cuerpo: sentencia.body })
    } else if (ts.isVariableStatement(sentencia)) {
      for (const d of sentencia.declarationList.declarations) {
        const ini = d.initializer
        if (ini && (ts.isArrowFunction(ini) || ts.isFunctionExpression(ini)) && ini.body
            && ts.isBlock(ini.body)) {
          salida.push({ nombre: d.name.getText(fuente), cuerpo: ini.body })
        }
      }
    }
  }
  return salida
}

function analizar(ruta) {
  const original = readFileSync(ruta, 'utf8')
  const fuente = ts.createSourceFile(
    ruta, original, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  )
  const ns = espacioDeNombres(ruta)
  const componentes = componentesDePrimerNivel(fuente)
  const hallazgos = []
  const usadas = new Map()

  function componenteDe(pos) {
    return componentes.find((c) => pos >= c.cuerpo.getStart(fuente) && pos < c.cuerpo.getEnd())
  }

  // El mismo texto reutiliza la misma clave. Sonaba a detalle y no lo es: en
  // `PortalUsersTab` «Permisos en el portal» sale dos veces y «Email de acceso»
  // otras dos. Con un contador ciego salen `_2` y `_3`, que son la misma frase
  // traducida dos veces y dos sitios donde se puede quedar desincronizada.
  // El sufijo solo aparece cuando dos textos DISTINTOS colisionan al pasar por
  // `aClave` — truncada a siete palabras, eso ocurre de verdad.
  const porTexto = new Map()

  function clavePara(texto) {
    if (porTexto.has(texto)) return porTexto.get(texto)
    const base = `${ns}.${aClave(texto)}`
    const n = (usadas.get(base) ?? 0) + 1
    usadas.set(base, n)
    const clave = n === 1 ? base : `${base}_${n}`
    porTexto.set(texto, clave)
    return clave
  }

  function visitar(nodo) {
    if (ts.isJsxText(nodo)) {
      const texto = nodo.text.trim()
      if (texto && CASTELLANO.test(texto)) {
        const inicio = nodo.getStart(fuente)
        // Solo el tramo con texto: se respetan los espacios y saltos de
        // alrededor, que en JSX son significativos para el hueco entre nodos.
        const desplazamiento = nodo.getFullText(fuente).indexOf(texto)
        const desde = nodo.getFullStart() + desplazamiento
        hallazgos.push({
          tipo: 'texto', texto, desde, hasta: desde + texto.length,
          clave: clavePara(texto), componente: componenteDe(inicio)?.nombre,
          cuerpo: componenteDe(inicio)?.cuerpo,
        })
      }
    } else if (ts.isJsxAttribute(nodo) && nodo.initializer
               && ATRIBUTOS_VISIBLES.has(nodo.name.getText(fuente))
               && ts.isStringLiteral(nodo.initializer)) {
      const texto = nodo.initializer.text.trim()
      if (texto && CASTELLANO.test(texto)) {
        const comp = componenteDe(nodo.getStart(fuente))
        hallazgos.push({
          tipo: 'atributo', texto,
          desde: nodo.initializer.getStart(fuente), hasta: nodo.initializer.getEnd(),
          clave: clavePara(texto), componente: comp?.nombre, cuerpo: comp?.cuerpo,
        })
      }
    }
    ts.forEachChild(nodo, visitar)
  }

  visitar(fuente)
  return { original, fuente, hallazgos, componentes }
}

function tieneHook(cuerpo, fuente) {
  return /const\s*\{[^}]*\bt\b[^}]*\}\s*=\s*useAppLang\(\)|const\s+t\s*=\s*useAppT\(\)/
    .test(cuerpo.getText(fuente))
}

function aplicar(ruta) {
  const { original, fuente, hallazgos } = analizar(ruta)
  if (!hallazgos.length) return { texto: original, claves: [] }

  const sinComponente = hallazgos.filter((h) => !h.cuerpo)
  if (sinComponente.length) {
    console.error(
      `  ! ${sinComponente.length} literales fuera de un componente de primer ` +
      'nivel; se dejan como estan y se listan al final.',
    )
  }
  const utiles = hallazgos.filter((h) => h.cuerpo)

  // Ediciones de atras hacia delante: asi ninguna mueve a la siguiente.
  const ediciones = utiles.map((h) => ({
    desde: h.desde, hasta: h.hasta,
    con: h.tipo === 'texto' ? `{t('${h.clave}')}` : `{t('${h.clave}')}`,
  }))

  // Y el hook, una vez por componente que lo necesite.
  const cuerposVistos = new Set()
  for (const h of utiles) {
    if (cuerposVistos.has(h.cuerpo)) continue
    cuerposVistos.add(h.cuerpo)
    if (tieneHook(h.cuerpo, fuente)) continue
    ediciones.push({
      desde: h.cuerpo.getStart(fuente) + 1, hasta: h.cuerpo.getStart(fuente) + 1,
      con: '\n  const { t } = useAppLang()',
    })
  }

  ediciones.sort((a, b) => b.desde - a.desde)
  let texto = original
  for (const e of ediciones) {
    texto = texto.slice(0, e.desde) + e.con + texto.slice(e.hasta)
  }

  if (!/from '[^']*i18n\/AppLangContext'/.test(texto)) {
    const lineas = texto.split('\n')
    const ultimo = lineas.reduce((acc, l, i) => (l.startsWith('import ') ? i : acc), 0)
    const prof = ruta.split(/[\\/]/).filter((x) => x && x !== '.').length - 2
    lineas.splice(ultimo + 1, 0,
      `import { useAppLang } from '${'../'.repeat(prof)}i18n/AppLangContext'`)
    texto = lineas.join('\n')
  }

  return { texto, claves: utiles.map((h) => [h.clave, h.texto]), sinComponente }
}

const rutas = process.argv.slice(2).filter((a) => !a.startsWith('--'))
const modo = process.argv.includes('--aplicar') ? 'aplicar' : 'plan'

for (const ruta of rutas) {
  if (modo === 'plan') {
    const { hallazgos } = analizar(ruta)
    console.log(`\n${ruta}: ${hallazgos.length} literales`)
    for (const h of hallazgos) {
      console.log(`  ${h.clave.padEnd(46)} ${h.componente ?? '(FUERA)'}  ${JSON.stringify(h.texto)}`)
    }
  } else {
    const { texto, claves, sinComponente } = aplicar(ruta)
    writeFileSync(ruta, texto, 'utf8')
    console.log(`\n// ${ruta}: ${claves.length} claves`)
    // Sin repetir: dos literales identicos comparten clave, y volcarla dos
    // veces invita a traducirla dos veces con dos redacciones distintas.
    const vistas = new Set()
    for (const [k, v] of claves) {
      if (vistas.has(k)) continue
      vistas.add(k)
      console.log(`${JSON.stringify(k)}: ${JSON.stringify(v)},`)
    }
    if (sinComponente?.length) {
      console.log(`// sin tocar (${sinComponente.length}): ` +
        sinComponente.map((h) => JSON.stringify(h.texto)).join(', '))
    }
  }
}
