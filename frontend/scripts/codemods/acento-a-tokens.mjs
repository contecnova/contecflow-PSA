// Codemod (auditoria 2026-11, #11): azul del acento fijo -> derivado de var(--accent).
//
// El azul del tema oscuro (#4f8ef7 = rgb(79,142,247)) aparecia escrito a mano
// con opacidad (`rgba(79,142,247,0.25)`, `'#4f8ef718'`). Con eso los temas
// freight/light/midnight/slate/alto contraste y el acento del perfil no llegaban
// a bordes, fondos y sombras. Cada aparicion se sustituye por:
//   - 20/30/40 %  -> var(--accent-border-soft | --accent-border | --accent-border-strong)
//                    (en index.css son color-mix del acento con ese mismo %)
//   - otro %      -> color-mix(in srgb, var(--accent) N%, transparent)
// En el tema oscuro el color resultante es el mismo; en los demas sigue al acento.
//
// Tambien convierte los hex de 8 digitos (#rrggbbAA) cuyo rrggbb es un token
// del :root (p. ej. '#34d39918' -> color-mix(in srgb, var(--success) 9%, transparent))
// y los hex de 6 digitos que son el valor COMPLETO de una cadena y coinciden con
// un token, pero solo en ficheros sin concatenacion de opacidad (`${c}22`,
// c + '1a'), sin canvas (getContext) y fuera de las exclusiones de
// colores-a-tokens.mjs: var() no se resuelve ahi.
//
// Idempotente: tras una pasada no queda ningun patron que coincida.
// Uso: node scripts/codemods/acento-a-tokens.mjs [--dry-run]
import fs from 'node:fs'
import path from 'node:path'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const dry = process.argv.includes('--dry-run')

const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
const root = css.slice(css.indexOf(':root'), css.indexOf('}', css.indexOf(':root')))
const porHex = new Map()
for (const m of root.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\s*;/g)) {
  const hex = normalizar(m[2])
  if (!porHex.has(hex)) porHex.set(hex, m[1])
}
function normalizar(h) {
  h = h.toLowerCase()
  return h.length === 4 ? '#' + [...h.slice(1)].map((c) => c + c).join('') : h
}
const pct = (a) => Math.round(a * 100)
function mezcla(token, p) {
  if (token === '--accent') {
    if (p === 20) return 'var(--accent-border-soft)'
    if (p === 30) return 'var(--accent-border)'
    if (p === 40) return 'var(--accent-border-strong)'
  }
  return `color-mix(in srgb, var(${token}) ${p}%, transparent)`
}

// Los rgba del acento se cambian en todos; los hex solo fuera de EXCLUIR_HEX.
// UserProfilePanel: sus presets de acento son DATOS (applyAccent exige #rrggbb).
const EXCLUIR_RUTA = [/[\\/]constants[\\/]theme/, /[\\/]i18n[\\/]/, /\.test\.tsx?$/, /[\\/]__tests__[\\/]/]
const EXCLUIR_HEX = [/[\\/]UserProfilePanel\.tsx$/, /[\\/]charts[\\/]/]
const CANVAS = /getContext\(/
const CONCAT = /\}[0-9a-fA-F]{2}[`'"\s;,)]|\+\s*['"`][0-9a-fA-F]{2}['"`]/

function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) yield* recorrer(p)
    else if (/\.(tsx|ts)$/.test(e.name)) yield p
  }
}

const RGBA = /rgba\(\s*79\s*,\s*142\s*,\s*247\s*,\s*(0?\.\d+|1|0)\s*\)/g
const HEX8 = /(['"`])(#[0-9a-fA-F]{6})([0-9a-fA-F]{2})\1/g
const HEX6 = /(['"])(#[0-9a-fA-F]{6})\1/g

const total = { rgba: 0, hex8: 0, hex6: 0, ficheros: 0 }
for (const f of recorrer(SRC)) {
  if (EXCLUIR_RUTA.some((r) => r.test(f))) continue
  const t = fs.readFileSync(f, 'utf8')
  if (CANVAS.test(t)) continue
  let n = t.replace(RGBA, (_, a) => { total.rgba++; return mezcla('--accent', pct(Number(a))) })
  if (!CONCAT.test(t) && !EXCLUIR_HEX.some((r) => r.test(f))) {
    n = n.replace(HEX8, (todo, q, hex, aa) => {
      const tok = porHex.get(normalizar(hex))
      if (!tok) return todo
      total.hex8++
      return `${q}${mezcla(tok, Math.round((parseInt(aa, 16) / 255) * 100))}${q}`
    })
    n = n.replace(HEX6, (todo, q, hex, off, str) => {
      const tok = porHex.get(normalizar(hex))
      if (!tok) return todo
      // Un hex que va a un <input type="color">, a la API o a una comparacion es
      // un dato: se deja. Se detecta por el contexto inmediato de la linea.
      const ini = str.lastIndexOf('\n', off) + 1
      const linea = str.slice(ini, str.indexOf('\n', off) === -1 ? undefined : str.indexOf('\n', off))
      if (/type=["']color|===|!==|useState|initial\??\.|accent_color|primary_color|color_hex|brand/i.test(linea)) return todo
      total.hex6++
      return `${q}var(${tok})${q}`
    })
  }
  if (n !== t) { total.ficheros++; if (!dry) fs.writeFileSync(f, n) }
}
// index.css: los rgba fijos del acento fuera de la definicion de los tokens base.
const cssNuevo = css.replace(RGBA, (todo, a) => { total.rgba++; return mezcla('--accent', pct(Number(a))) })
if (cssNuevo !== css && !dry) fs.writeFileSync(path.join(SRC, 'index.css'), cssNuevo)
console.log(`${dry ? '[dry] ' : ''}rgba acento: ${total.rgba}; hex+alfa: ${total.hex8}; hex de token: ${total.hex6}; ficheros .ts/.tsx: ${total.ficheros}`)
