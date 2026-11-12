// Codemod (auditoria 2026-11): colores hex fijos -> tokens del tema.
//
// Solo cambia un hex cuando coincide EXACTAMENTE con el valor de un token del
// tema base (`:root` de src/index.css). Asi la pantalla se ve igual en el tema
// base y pasa a seguir a los demas temas y al acento del perfil. Los hex que no
// son de ningun token no se tocan: elegir "el mas parecido" cambiaria el color
// sin que nadie lo haya decidido. Se listan para revisarlos a mano.
//
// No toca ficheros donde `var()` no se resuelve: canvas (getContext) y
// librerias que pintan fuera del DOM (echarts, plotly, d3).
//
// Uso: node scripts/codemods/colores-a-tokens.mjs [--dry-run]
import fs from 'node:fs'
import path from 'node:path'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const dry = process.argv.includes('--dry-run')

// Tokens del :root (el primer bloque) de index.css.
const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
const root = css.slice(css.indexOf(':root'), css.indexOf('}', css.indexOf(':root')))
const porHex = new Map()
for (const m of root.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\s*;/g)) {
  const hex = normalizar(m[2])
  // El primero declarado gana: es el nombre canonico (--bg es alias de --surface-0, etc.).
  if (!porHex.has(hex)) porHex.set(hex, m[1])
}

function normalizar(h) {
  h = h.toLowerCase()
  return h.length === 4 ? '#' + [...h.slice(1)].map((c) => c + c).join('') : h
}

// UserProfilePanel: sus presets de acento son DATOS (se guardan como
// accent_color y applyAccent() exige #rrggbb). La primera pasada los convirtio
// a var() y dejo 7 de 8 presets sin efecto; no debe volver a tocarlos.
const EXCLUIR_RUTA = [/[\\/]charts[\\/]/, /[\\/]constants[\\/]theme/, /[\\/]i18n[\\/]/, /\.test\.tsx?$/, /[\\/]__tests__[\\/]/, /[\\/]UserProfilePanel\.tsx$/]
// Tambien se saltan los ficheros que pegan opacidad a un color (`${c}22`,
// `c + '1a'`): con `var()` eso es CSS invalido (guia de diseno, 2.4).
const EXCLUIR_CONTENIDO = /getContext\(|from ['"](echarts|echarts-for-react|plotly|react-plotly\.js|d3)['"]|\}[0-9a-fA-F]{2}[`'"\s;,)]|\+\s*['"`][0-9a-fA-F]{2}['"`]/

function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) yield* recorrer(p)
    else if (/\.(tsx|ts)$/.test(e.name)) yield p
  }
}

let cambiados = 0
let sustituciones = 0
const pendientes = new Map()
for (const fichero of recorrer(SRC)) {
  if (EXCLUIR_RUTA.some((r) => r.test(fichero))) continue
  const texto = fs.readFileSync(fichero, 'utf8')
  if (EXCLUIR_CONTENIDO.test(texto)) continue
  let n = 0
  // Solo hex que son el valor COMPLETO de una propiedad de estilo
  // (`color: '#abc'`, `fill="#aabbcc"`). Un hex que es un dato (el valor de un
  // selector de color, lo que se guarda en la API) no se toca: `var()` ahi lo
  // romperia. Tampoco uno dentro de una cadena mayor (gradientes, sombras).
  const PROPIEDAD = /(\b(?:color|background|backgroundColor|borderColor|border(?:Top|Bottom|Left|Right)Color|outlineColor|fill|stroke|stopColor|caretColor|accentColor)\s*[:=]\s*\{?\s*)(['"])(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\2/g
  const nuevo = texto.replace(PROPIEDAD, (todo, prefijo, q, hex) => {
    const token = porHex.get(normalizar(hex))
    if (!token) {
      pendientes.set(path.relative(RAIZ, fichero), (pendientes.get(path.relative(RAIZ, fichero)) || 0) + 1)
      return todo
    }
    n++
    return `${prefijo}${q}var(${token})${q}`
  })
  if (n) {
    cambiados++
    sustituciones += n
    if (!dry) fs.writeFileSync(fichero, nuevo)
  }
}

console.log(`${sustituciones} colores en ${cambiados} ficheros ${dry ? 'a cambiar' : 'cambiados'}`)
const total = [...pendientes.values()].reduce((a, b) => a + b, 0)
console.log(`${total} hex sin token exacto en ${pendientes.size} ficheros (revisar a mano):`)
for (const [f, c] of [...pendientes].sort((a, b) => b[1] - a[1]).slice(0, 15)) console.log(`  ${c}\t${f}`)
