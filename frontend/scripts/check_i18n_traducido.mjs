// ¿Está TODO traducido? Vigilante del barrido de traducciones (24-11-2026).
//
// Los medidores que ya había miran trozos: `check_i18n_coverage` (claves de es que
// faltan en en/zh), `check_i18n_literales` (texto a pelo en JSX y en seis atributos),
// `check_i18n_claves_sin_definir` (t('x.y') sin clave). Ninguno veía:
//
//   1. valores de en/zh COPIADOS del castellano (la clave existe, el texto no está
//      traducido): «al 100 %» y la pantalla en castellano;
//   2. el portal de clientes (8 idiomas, diccionarios propios en i18n/portal/*.ts):
//      claves que faltan o sobran en un idioma y valores copiados del castellano;
//   3. literales en castellano fuera del JSX: `label: 'Pendiente'` en un objeto que
//      se pinta, `toast.error('No se pudo…')`, `confirm('¿Seguro…?')`, `throw new
//      Error('…')`, cadenas dentro de `{cond ? 'Sí' : 'No'}` o de una plantilla;
//   4. claves pedidas a t() que no están ni en el operador ni en el portal.
//
// Es un trinquete: lo que hay hoy y es legítimo (nombres propios, siglas, marcas,
// respaldos de una clave que sí existe) está en `i18n_traducido_baseline.json`.
// Falla si aparece algo NUEVO; si algo de la lista desaparece, avisa para encogerla
// (`--actualizar` la regenera con lo medido; revisar el diff: solo puede encoger).
//
// Uso:
//   node scripts/check_i18n_traducido.mjs              gate
//   node scripts/check_i18n_traducido.mjs --detalle    lista lo nuevo con fichero y línea
//   node scripts/check_i18n_traducido.mjs --actualizar reescribe la lista blanca
//
// Contenido traducible del servidor (biblioteca de Certificaciones…): lo vigila
// `tests/test_certificaciones_traduccion_2026_11.py`. Guía: docs/GUIA_DE_DISENO.md §10.
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const FUENTES = join(RAIZ, 'src')
const BASE = join(RAIZ, 'scripts', 'i18n_traducido_baseline.json')
const DETALLE = process.argv.includes('--detalle')
const ACTUALIZAR = process.argv.includes('--actualizar')

const cargar = async p => (await import(pathToFileURL(join(RAIZ, p)).href)).default
const OPERADOR = { es: await cargar('src/i18n/langs/es.mjs'), en: await cargar('src/i18n/langs/en.mjs'), zh: await cargar('src/i18n/langs/zh.mjs') }
const IDIOMAS_PORTAL = ['es', 'en', 'fr', 'de', 'pt', 'it', 'pl', 'zh']

function cargarPortal(code) {
  const src = readFileSync(join(RAIZ, 'src/i18n/portal', `${code}.ts`), 'utf8')
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const m = { exports: {} }
  new Function('module', 'exports', 'require', js)(m, m.exports, () => ({}))
  return m.exports.default
}
const PORTAL = Object.fromEntries(IDIOMAS_PORTAL.map(c => [c, cargarPortal(c)]))

const hojas = (obj, pref = '', out = {}) => {
  for (const [k, v] of Object.entries(obj || {})) {
    const key = pref ? `${pref}.${k}` : k
    if (v && typeof v === 'object') hojas(v, key, out)
    else if (typeof v === 'string') out[key] = v
  }
  return out
}
const OP = { es: hojas(OPERADOR.es), en: hojas(OPERADOR.en), zh: hojas(OPERADOR.zh) }

// Iguales que no hace falta apuntar: sin letras, una variable sola, siglas y códigos,
// correos y URL, identificadores técnicos.
function igualEvidente(v) {
  const s = v.trim()
  if (!/[A-Za-zÀ-ÿ]/.test(s)) return true
  if (/^\{\{?[\w.]+\}?\}$/.test(s)) return true
  if (/^[A-Z0-9_\-./:+&() ]{1,12}$/.test(s)) return true
  if (/^[\w.+-]+@[\w.-]+$/.test(s) || /^https?:\/\//.test(s)) return true
  return false
}

const hallado = { iguales: [], faltan: [], sobran: [], literales: [], sinDefinir: [] }

for (const l of ['en', 'zh']) {
  for (const [k, v] of Object.entries(OP.es)) {
    if (!(k in OP[l])) hallado.faltan.push(`operador.${l}:${k}`)
    else if (OP[l][k] === v && !igualEvidente(v)) hallado.iguales.push(`operador.${l}:${k}`)
  }
}
for (const l of IDIOMAS_PORTAL.filter(c => c !== 'es')) {
  for (const [k, v] of Object.entries(PORTAL.es)) {
    if (!(k in PORTAL[l])) hallado.faltan.push(`portal.${l}:${k}`)
    else if (PORTAL[l][k] === v && !igualEvidente(v)) hallado.iguales.push(`portal.${l}:${k}`)
  }
  for (const k of Object.keys(PORTAL[l])) if (!(k in PORTAL.es)) hallado.sobran.push(`portal.${l}:${k}`)
}

// ── Código ──────────────────────────────────────────────────────────────────
const CASTELLANO = /[áéíóúñÁÉÍÓÚÑ¿¡]|\b(de|la|el|los|las|del|para|con|sin|por|que|una|se|su|al|más|este|esta|hay|son|como|cuando|todos|todas|nuevo|nueva|guardar|cancelar|borrar|eliminar|crear|editar|buscar|cargando|sí)\b/i
const CLASES_CSS = /^[a-z0-9_-]+(\s+[a-z0-9_-]+)*$/
const PROPS_VISIBLES = new Set(['label', 'etiqueta', 'title', 'titulo', 'placeholder', 'mensaje', 'message', 'description',
  'descripcion', 'texto', 'text', 'tooltip', 'ayuda', 'subtitle', 'subtitulo', 'header', 'cabecera', 'emptyText',
  'vacio', 'confirmText', 'cancelText', 'ariaLabel', 'alt', 'hint', 'aviso', 'detalle'])
const ATRIBUTOS = new Set(['placeholder', 'title', 'label', 'aria-label', 'alt', 'aria-placeholder', 'subtitle', 'etiqueta',
  'titulo', 'mensaje', 'texto', 'descripcion', 'tooltip', 'ayuda', 'emptyText', 'confirmText', 'cancelText', 'description', 'ariaLabel'])
const LLAMADAS = /^(toast\.(success|error|info|warning|warn)|(window\.)?(confirm|alert|prompt)|notify|mostrarError|setError|setMensaje|setAviso)$/
const FUNCIONES_T = /^(t|tp|tr|traducir|traducirSinHook|i18n\.t)$/
// Diccionarios de texto en castellano por diseño (tienen su en/zh al lado).
const FUENTES_DE_TEXTO = /\/i18n\/|\/textos\/es\.ts$|\/textosLineales\/es\.ts$|\/textos\/es\.mjs$/

function ficheros(dir) {
  const out = []
  for (const e of readdirSync(dir)) {
    const p = join(dir, e)
    if (statSync(p).isDirectory()) { if (!['__tests__', 'node_modules'].includes(e)) out.push(...ficheros(p)) }
    else if (/\.(tsx?|mjs)$/.test(p) && !/\.test\.|\.spec\.|\.d\.ts$/.test(p)) out.push(p)
  }
  return out
}

const clavesOperador = new Set(Object.keys(OP.es))
const clavesPortal = new Set(Object.keys(PORTAL.es))

for (const f of ficheros(FUENTES)) {
  const rel = relative(RAIZ, f).replaceAll('\\', '/')
  const sf = ts.createSourceFile(f, readFileSync(f, 'utf8'), ts.ScriptTarget.Latest, true,
    f.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const esTexto = FUENTES_DE_TEXTO.test('/' + rel)
  const apuntar = (nodo, tipo, texto) => {
    const s = texto.replace(/\s+/g, ' ').trim()
    if (s.length < 2 || !CASTELLANO.test(s) || CLASES_CSS.test(s) || /^[\w./-]+$/.test(s)) return
    const linea = sf.getLineAndCharacterOfPosition(nodo.getStart()).line + 1
    hallado.literales.push({ id: `${rel}|${tipo}|${s}`, linea })
  }
  const enJsx = n => { for (let p = n.parent; p; p = p.parent) { if (ts.isJsxElement(p) || ts.isJsxFragment(p) || ts.isJsxSelfClosingElement(p)) return true; if (ts.isFunctionLike(p) || ts.isSourceFile(p)) return false } return false }
  const dentroDeT = n => { for (let p = n.parent; p && !ts.isSourceFile(p); p = p.parent) { if (ts.isCallExpression(p) && FUNCIONES_T.test(p.expression.getText(sf))) return true; if (ts.isFunctionLike(p)) return false } return false }
  const nombreProp = p => p.name.getText(sf).replace(/['"]/g, '')
  const visitar = n => {
    if (!esTexto) {
      if (ts.isJsxText(n)) apuntar(n, 'jsx', n.text)
      else if (ts.isJsxAttribute(n) && n.initializer && ts.isStringLiteral(n.initializer) && ATRIBUTOS.has(n.name.getText(sf))) {
        apuntar(n, 'atributo', n.initializer.text)
      } else if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && !dentroDeT(n)) {
        const p = n.parent
        if (ts.isJsxExpression(p) || (ts.isConditionalExpression(p) && enJsx(p))
          || (ts.isBinaryExpression(p) && enJsx(p) && ![ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken].includes(p.operatorToken.kind))) apuntar(n, 'expresion', n.text)
        else if (ts.isPropertyAssignment(p) && p.initializer === n && PROPS_VISIBLES.has(nombreProp(p))) apuntar(n, 'propiedad', n.text)
        else if (ts.isCallExpression(p) && LLAMADAS.test(p.expression.getText(sf))) apuntar(n, 'llamada', n.text)
        else if (ts.isNewExpression(p) && /Error$/.test(p.expression.getText(sf))) apuntar(n, 'error', n.text)
      } else if (ts.isTemplateExpression(n) && !dentroDeT(n)) {
        const p = n.parent
        const txt = n.head.text + n.templateSpans.map(s => ' ' + s.literal.text).join('')
        if (ts.isJsxExpression(p) || (ts.isCallExpression(p) && LLAMADAS.test(p.expression.getText(sf)))
          || (ts.isPropertyAssignment(p) && PROPS_VISIBLES.has(nombreProp(p)))) apuntar(n, 'plantilla', txt)
      }
    }
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && ['t', 'traducir', 'traducirSinHook'].includes(n.expression.text)
      && n.arguments.length >= 1 && ts.isStringLiteral(n.arguments[0])) {
      const k = n.arguments[0].text
      if (k.includes('.') && !clavesOperador.has(k) && !clavesPortal.has(k)) hallado.sinDefinir.push(`${k}|${rel}`)
    }
    ts.forEachChild(n, visitar)
  }
  visitar(sf)
}

// ── Trinquete ───────────────────────────────────────────────────────────────
const medido = {
  iguales: [...new Set(hallado.iguales)].sort(),
  faltan: [...new Set(hallado.faltan)].sort(),
  sobran: [...new Set(hallado.sobran)].sort(),
  literales: [...new Set(hallado.literales.map(x => x.id))].sort(),
  sinDefinir: [...new Set(hallado.sinDefinir)].sort(),
}

if (ACTUALIZAR) {
  writeFileSync(BASE, JSON.stringify({
    nota: 'Lista blanca de check_i18n_traducido.mjs (24-11-2026). Solo puede encoger: nombres propios, siglas, '
      + 'marcas y respaldos de claves que existen. Ver docs/GUIA_DE_DISENO.md §10.',
    ...medido,
  }, null, 1) + '\n', 'utf8')
  console.log(`Lista blanca reescrita: ${Object.entries(medido).map(([k, v]) => `${k} ${v.length}`).join(' · ')}`)
  process.exit(0)
}

let base = { iguales: [], faltan: [], sobran: [], literales: [], sinDefinir: [] }
try { base = JSON.parse(readFileSync(BASE, 'utf8')) } catch { /* sin lista: todo es nuevo */ }

let nuevos = 0
const lineaDe = id => hallado.literales.find(x => x.id === id)?.linea
for (const tipo of Object.keys(medido)) {
  const permitido = new Set(base[tipo] || [])
  const nuevo = medido[tipo].filter(x => !permitido.has(x))
  const resuelto = (base[tipo] || []).filter(x => !medido[tipo].includes(x))
  console.log(`${nuevo.length ? '✗' : '✓'} ${tipo}: ${medido[tipo].length} (lista blanca ${permitido.size}${nuevo.length ? `, ${nuevo.length} NUEVOS` : ''}${resuelto.length ? `, ${resuelto.length} ya resueltos: encoge la lista con --actualizar` : ''})`)
  if (nuevo.length && (DETALLE || nuevo.length <= 25)) {
    for (const x of nuevo) console.log(`    ${x}${tipo === 'literales' ? `  (línea ${lineaDe(x)})` : ''}`)
  }
  nuevos += nuevo.length
}
if (nuevos) {
  console.error(`\n✗ ${nuevos} textos sin traducir nuevos. Todo lo que lee el usuario pasa por t() con su clave en es/en/zh`
    + ' (y en los 8 idiomas del portal); en/zh no pueden copiar el castellano. Ver docs/GUIA_DE_DISENO.md §10.')
  process.exit(1)
}
console.log('\n✓ Nada nuevo sin traducir.')
