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

// Entidades HTML: en el JSX las decodifica el propio parser, asi que
// `pulsa &quot;+ KR&quot;` se ve en pantalla con comillas de verdad. Metida tal
// cual en el diccionario, `t()` devuelve la cadena SIN decodificar y React la
// pinta escapada: el usuario leeria `&quot;`. Se decodifican al capturar.
const ENTIDADES = {
  '&quot;': '"', '&apos;': "'", '&amp;': '&', '&lt;': '<', '&gt;': '>',
  '&nbsp;': ' ', '&hellip;': '…', '&mdash;': '—', '&ndash;': '–',
}

function decodificar(texto) {
  return texto
    .replace(/&(?:quot|apos|amp|lt|gt|nbsp|hellip|mdash|ndash);/g, (e) => ENTIDADES[e])
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
}

function aClave(texto) {
  return sinAcentos(texto)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .split('_').filter(Boolean).slice(0, 7).join('_') || 'texto'
}

function espacioDeNombres(ruta) {
  // Los sufijos largos PRIMERO: con `Tab` antes que `Tabs`, `ClientsPageTabs`
  // se quedaba en `Clientss` —la `s` huerfana de `Tabs`— y el namespace era
  // `clientss`, que parece una errata y confunde a quien busque la clave.
  const base = basename(ruta).replace(/\.tsx$/, '')
    .replace(/Sections|Tabs|Panel|Page|Tab/g, '')
  return aClave(base)
}

/** Un componente de React: función de primer nivel con nombre en Mayúscula. */
function esNombreDeComponente(nombre) {
  return /^[A-Z]/.test(nombre)
}

/** Las funciones de primer nivel del modulo que SON componentes, con su rango.
 *
 * La mayúscula inicial no es cosmética: es la regla con la que React distingue
 * un componente de una función corriente, y por tanto dónde puede vivir un
 * hook. `WikiPage` tiene una `renderBlocks(blocks)` de primer nivel que
 * devuelve JSX pero que se llama como función normal desde el render de dos
 * componentes; meterle `useAppT()` es una violación de las reglas de los hooks
 * —ESLint la marcó— y en ejecución descoloca el orden de los hooks del
 * componente que la invoca, que es de los fallos que aparecen tarde y mal.
 *
 * En esas funciones los literales se dejan sin tocar y se listan al final: el
 * arreglo correcto es pasarles `t` por parámetro, y eso lo decide quien lee el
 * código, no un barrido.
 */
function componentesDePrimerNivel(fuente) {
  const salida = []
  for (const sentencia of fuente.statements) {
    if (ts.isFunctionDeclaration(sentencia) && sentencia.body) {
      const nombre = sentencia.name?.getText(fuente) ?? '?'
      if (esNombreDeComponente(nombre)) salida.push({ nombre, cuerpo: sentencia.body })
    } else if (ts.isVariableStatement(sentencia)) {
      for (const d of sentencia.declarationList.declarations) {
        const ini = d.initializer
        const nombre = d.name.getText(fuente)
        if (ini && (ts.isArrowFunction(ini) || ts.isFunctionExpression(ini)) && ini.body
            && ts.isBlock(ini.body) && esNombreDeComponente(nombre)) {
          salida.push({ nombre, cuerpo: ini.body })
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
      const crudo = nodo.text.trim()
      const texto = decodificar(crudo)
      if (crudo && CASTELLANO.test(texto)) {
        const inicio = nodo.getStart(fuente)
        // Solo el tramo con texto: se respetan los espacios y saltos de
        // alrededor, que en JSX son significativos para el hueco entre nodos.
        // El desplazamiento se busca con el texto CRUDO: la posicion es la del
        // fichero, donde la entidad sigue escrita. Lo decodificado es el valor
        // que va al diccionario, no lo que se recorta del fuente.
        const desplazamiento = nodo.getFullText(fuente).indexOf(crudo)
        const desde = nodo.getFullStart() + desplazamiento
        hallazgos.push({
          tipo: 'texto', texto, desde, hasta: desde + crudo.length,
          clave: clavePara(texto), componente: componenteDe(inicio)?.nombre,
          cuerpo: componenteDe(inicio)?.cuerpo,
        })
      }
    } else if (ts.isJsxAttribute(nodo) && nodo.initializer
               && ATRIBUTOS_VISIBLES.has(nodo.name.getText(fuente))
               && ts.isStringLiteral(nodo.initializer)) {
      const texto = decodificar(nodo.initializer.text.trim())
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

// Se pregunta por el NOMBRE que se va a emitir, no por «¿hay algún hook?».
//
// Con `traducir` costó un segundo typecheck en rojo: varios componentes ya
// tenían `const t = useAppT()`, la comprobación decía «ya lo tiene» y no
// insertaba nada — pero las llamadas emitidas eran `traducir(...)`. El hook que
// hay no sirve si no se llama como lo que se escribe.
function tieneHook(cuerpo, fuente, nombre) {
  const n = nombre.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(
    // Destructurado, de cualquiera de los dos hooks que devuelven objeto.
    `const\\s*\\{[^}]*\\b${n}\\b[^}]*\\}\\s*=\\s*use(?:AppLang|AppT)\\(\\)`
    // O directo, que es lo que devuelve el `useAppT` de AppLangContext.
    + `|const\\s+${n}\\s*=\\s*useAppT\\(\\)`,
  ).test(cuerpo.getText(fuente))
}

// Hay DOS formas de pedir `t` en este proyecto y las dos estan en uso:
// `const { t } = useAppLang()` y el atajo `const t = useAppT()`. Se usa la que
// el fichero ya importe.
//
// Comprobarlo por la RUTA del import no basta y costo un typecheck en rojo:
// `OKRsPage` y `SprintsPage` ya importaban de `i18n/AppLangContext`, asi que la
// comprobacion daba «import puesto» y no anadia nada — pero lo que importaban
// era `useAppT`, y el hook insertado llamaba a `useAppLang`, que ahi no existe.
// La comprobacion es por el NOMBRE, no por el modulo.
/** ¿Hay en el fichero algún `t` que NO sea la función de traducción? */
function tEstaOcupado(fuente) {
  let ocupado = false
  function visitar(nodo) {
    if (ocupado) return
    // Un parámetro llamado `t` — `tabs.map(t => …)`, que es el caso real.
    if (ts.isParameter(nodo) && ts.isIdentifier(nodo.name) && nodo.name.text === 't') {
      ocupado = true
      return
    }
    // O una variable `const t = …` que no salga de los hooks de traducción.
    if (ts.isVariableDeclaration(nodo) && ts.isIdentifier(nodo.name) && nodo.name.text === 't') {
      const origen = nodo.initializer?.getText(fuente) ?? ''
      if (!/useAppT\(\)|useAppLang\(\)/.test(origen)) ocupado = true
      return
    }
    ts.forEachChild(nodo, visitar)
  }
  visitar(fuente)
  return ocupado
}

// Hay DOS formas de pedir la función en este proyecto y las dos están en uso:
// `const { t } = useAppLang()` y el atajo `const t = useAppT()`. Se usa la que
// el fichero ya importe.
//
// Y si el nombre `t` ya significa otra cosa en ese fichero, se usa `traducir`.
// No es hipotético: `PerformanceReviewsPage` recorre sus pestañas con
// `.map(t => …)`, así que dentro de ese callback `t` es un objeto con `label` y
// `help`. El hook insertado arriba quedaba tapado y `t('clave')` se compilaba
// como «llamar a un objeto». Lo cazó el typecheck estricto, pero en un fichero
// sin tipos habría llegado a producción como un fallo en tiempo de ejecución
// dentro de una lista.
// ── Hay TRES formas de pedir la función, y dos se llaman igual ───────────────
//
// `i18n/AppLangContext` exporta `useAppT()` que devuelve **la función**, y
// `hooks/useAppT` exporta otro `useAppT()` que devuelve **un objeto** con `.t`
// dentro. Mismo nombre, formas incompatibles, y la única manera de saber cuál
// es mirar de dónde viene el import. Dar por hecha la primera compilaba
// `t(...)` sobre un objeto en `ITSMKnowledgeTab`: `Type 'AppT' has no call
// signatures`. Queda anotado como hallazgo aparte: dos hooks públicos con el
// mismo nombre y distinto contrato son una trampa para cualquiera.
function fuenteDelImport(fuente, nombre) {
  for (const s of fuente.statements) {
    if (!ts.isImportDeclaration(s) || !s.importClause?.namedBindings) continue
    const b = s.importClause.namedBindings
    if (!ts.isNamedImports(b)) continue
    if (b.elements.some((e) => e.name.text === nombre)) return s.moduleSpecifier.getText(fuente)
  }
  return null
}

function formaDelHook(texto, fuente) {
  const nombreT = tEstaOcupado(fuente) ? 'traducir' : 't'
  const destructura = nombreT === 't' ? 't' : `t: ${nombreT}`
  const origen = fuenteDelImport(fuente, 'useAppT')

  if (origen && /hooks\/useAppT/.test(origen)) {
    return { llamada: `const { ${destructura} } = useAppT()`, nombre: 'useAppT', t: nombreT }
  }
  if (origen) {
    return { llamada: `const ${nombreT} = useAppT()`, nombre: 'useAppT', t: nombreT }
  }
  return {
    llamada: `const { ${destructura} } = useAppLang()`, nombre: 'useAppLang', t: nombreT,
  }
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
  const hook = formaDelHook(original, fuente)
  const ediciones = utiles.map((h) => ({
    desde: h.desde, hasta: h.hasta,
    con: `{${hook.t}('${h.clave}')}`,
  }))

  // Y el hook, una vez por componente que lo necesite, en la forma que el
  // fichero ya usa.
  const cuerposVistos = new Set()
  for (const h of utiles) {
    if (cuerposVistos.has(h.cuerpo)) continue
    cuerposVistos.add(h.cuerpo)
    if (tieneHook(h.cuerpo, fuente, hook.t)) continue
    ediciones.push({
      desde: h.cuerpo.getStart(fuente) + 1, hasta: h.cuerpo.getStart(fuente) + 1,
      con: `\n  ${hook.llamada}`,
    })
  }

  ediciones.sort((a, b) => b.desde - a.desde)
  let texto = original
  for (const e of ediciones) {
    texto = texto.slice(0, e.desde) + e.con + texto.slice(e.hasta)
  }

  // El import, sólo si el NOMBRE que se va a llamar no está ya traído.
  //
  // La línea va después del ÚLTIMO import según el AST, no según el texto.
  // Buscar «la última línea que empieza por import » mete la línea nueva en
  // medio de un import multilínea: en `PortalAdvancedSections` la última línea
  // así es `import {`, que abre una lista de doce nombres, y el fichero dejó de
  // parsear entero.
  if (!new RegExp(`\\b${hook.nombre}\\b`).test(original)) {
    const imports = fuente.statements.filter(ts.isImportDeclaration)
    const prof = ruta.split(/[\\/]/).filter((x) => x && x !== '.').length - 2
    const linea = `\nimport { ${hook.nombre} } from '${'../'.repeat(prof)}i18n/AppLangContext'`
    if (imports.length) {
      // El corte se calcula sobre el ORIGINAL y se traslada al texto ya
      // editado: todas las ediciones anteriores caen dentro del JSX, que va
      // después de los imports, así que el desplazamiento hasta aquí es cero.
      const corte = imports[imports.length - 1].getEnd()
      texto = texto.slice(0, corte) + linea + texto.slice(corte)
    } else {
      texto = `${linea.trimStart()}\n${texto}`
    }
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
