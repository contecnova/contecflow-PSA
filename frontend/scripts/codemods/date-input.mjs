// Codemod (auditoria 2026-11, #31): <input type="date|datetime-local"> -> <DateInput>.
//
// Solo toca <input> nativos cuyo `type` es un literal 'date' o 'datetime-local'.
// Los `type={cond ? 'date' : 'text'}` (campos polimorficos) y el <Input> del
// sistema de diseno no se tocan. El resto de props se conservan tal cual; el
// `type` se quita (datetime-local pasa a `withTime`). Anade el import relativo a
// src/components/ui/DateInput. Idempotente: una segunda pasada no cambia nada.
//
// Uso: node scripts/codemods/date-input.mjs [--dry-run]
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const COMPONENTE = path.join(SRC, 'components', 'ui', 'DateInput')
const dry = process.argv.includes('--dry-run')

function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) yield* recorrer(p)
    else if (/\.(tsx|jsx)$/.test(e.name) && !/\.test\./.test(e.name) && !p.includes('__tests__')) yield p
  }
}

function visitar(nodo, fn) {
  if (!nodo || typeof nodo.type !== 'string') return
  fn(nodo)
  for (const k of Object.keys(nodo)) {
    if (k === 'loc' || k === 'start' || k === 'end') continue
    const v = nodo[k]
    if (Array.isArray(v)) v.forEach((h) => h && typeof h.type === 'string' && visitar(h, fn))
    else if (v && typeof v.type === 'string') visitar(v, fn)
  }
}

let ficheros = 0
let campos = 0
for (const fichero of recorrer(SRC)) {
  if (fichero.startsWith(COMPONENTE)) continue
  const texto = fs.readFileSync(fichero, 'utf8')
  if (!/type=["'](date|datetime-local)["']/.test(texto)) continue
  const ast = parse(texto, { sourceType: 'module', plugins: ['jsx', 'typescript'] })
  const cambios = [] // [inicio, fin, reemplazo]
  visitar(ast.program, (n) => {
    if (n.type !== 'JSXOpeningElement' || n.name.type !== 'JSXIdentifier' || n.name.name !== 'input') return
    const attr = n.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === 'type')
    if (!attr || !attr.value || attr.value.type !== 'StringLiteral') return
    const tipo = attr.value.value
    if (tipo !== 'date' && tipo !== 'datetime-local') return
    cambios.push([n.name.start, n.name.end, 'DateInput'])
    if (tipo === 'datetime-local') cambios.push([attr.start, attr.end, 'withTime'])
    else {
      // Quita el atributo y el espacio que lo precede.
      let ini = attr.start
      while (ini > 0 && /[ \t]/.test(texto[ini - 1])) ini--
      let fin = attr.end
      if (/[\r\n]/.test(texto[ini - 1])) {
        // En su propia linea: si no hay nada mas en ella, se quita la linea entera.
        let f = attr.end
        while (/[ \t]/.test(texto[f])) f++
        if (texto[f] === '\r') f++
        if (texto[f] === '\n') fin = f + 1
        else ini = attr.start
      }
      if (ini === attr.start) while (/[ \t]/.test(texto[fin])) fin++
      cambios.push([ini, fin, ''])
    }
    campos++
  })
  if (!cambios.length) continue
  let nuevo = texto
  for (const [ini, fin, rep] of cambios.sort((a, b) => b[0] - a[0])) nuevo = nuevo.slice(0, ini) + rep + nuevo.slice(fin)
  // Import, tras el ultimo import del fichero.
  const yaImporta = ast.program.body.some((s) => s.type === 'ImportDeclaration' && s.specifiers.some((sp) => sp.local.name === 'DateInput'))
  if (!yaImporta) {
    let rel = path.relative(path.dirname(fichero), COMPONENTE).split(path.sep).join('/')
    if (!rel.startsWith('.')) rel = './' + rel
    const imports = ast.program.body.filter((s) => s.type === 'ImportDeclaration')
    const linea = `import DateInput from '${rel}'\n`
    if (imports.length) {
      const ultimo = imports[imports.length - 1].end
      const finLinea = texto.indexOf('\n', ultimo) + 1
      nuevo = nuevo.slice(0, finLinea) + linea + nuevo.slice(finLinea) // finLinea es anterior a todos los cambios
    } else nuevo = linea + nuevo
  }
  ficheros++
  if (!dry) fs.writeFileSync(fichero, nuevo)
}
console.log(`${campos} campos de fecha en ${ficheros} ficheros ${dry ? 'a migrar' : 'migrados'} a <DateInput>`)
