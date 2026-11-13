// Codemod (auditoria 2026-11, #41): zIndex numericos -> tokens var(--z-*).
//
// Solo cambia los valores que coinciden EXACTAMENTE con un token de index.css
// (50 sticky, 90 sidebar, 100 mobile-nav, 200 dropdown, 400 popover, 800 drawer,
// 1000 modal, 9999 drag): el orden de apilado queda igual. Los valores locales
// (1, 2, 10...: apilado dentro de un componente) y los que no son de ningun
// token (499, 500, 1100...) no se tocan: cambiarlos alteraria que tapa a que.
//
// Idempotente. Uso: node scripts/codemods/zindex-a-tokens.mjs [--dry-run]
import fs from 'node:fs'
import path from 'node:path'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const dry = process.argv.includes('--dry-run')
const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
const porValor = new Map()
for (const m of css.matchAll(/(--z-[\w-]+)\s*:\s*(\d+)\s*;/g)) if (!porValor.has(m[2])) porValor.set(m[2], m[1])

function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) yield* recorrer(p)
    else if (/\.tsx$/.test(e.name) && !/\.test\./.test(e.name)) yield p
  }
}
let n = 0, ficheros = 0
for (const f of recorrer(SRC)) {
  const t = fs.readFileSync(f, 'utf8')
  const nuevo = t.replace(/\bzIndex:(\s*)(\d+)\b/g, (todo, esp, v) => {
    const tok = porValor.get(v)
    if (!tok || Number(v) < 50) return todo
    n++
    return `zIndex:${esp}'var(${tok})'`
  })
  if (nuevo !== t) { ficheros++; if (!dry) fs.writeFileSync(f, nuevo) }
}
console.log(`${dry ? '[dry] ' : ''}zIndex a token: ${n} en ${ficheros} ficheros`)
