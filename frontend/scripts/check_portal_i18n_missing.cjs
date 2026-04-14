// Script para detectar claves de traducción faltantes en PORTAL_TRANSLATIONS
const fs = require('fs')
const path = require('path')


const file = path.join(__dirname, '../src/i18n/portalTranslations.js')
let src = fs.readFileSync(file, 'utf8')

// Eliminar export statements para poder evaluar
src = src.replace(/export\s+(const|function|default)\s+/g, '')

// Eval para obtener los objetos de traducción (es, en, ...)
let es, en, fr, de, pt, it, pl, zh
try {
  eval(src)
} catch (e) {
  console.error('Error evaluando portalTranslations.js:', e)
  process.exit(1)
}

const langs = { es, en, fr, de, pt, it, pl, zh }
const baseKeys = Object.keys(es)

let missing = {}
for (const [lang, obj] of Object.entries(langs)) {
  const missingKeys = baseKeys.filter(k => !(k in obj))
  if (missingKeys.length) missing[lang] = missingKeys
}

if (Object.keys(missing).length === 0) {
  console.log('✅ Todas las claves están presentes en todos los idiomas.')
} else {
  for (const [lang, keys] of Object.entries(missing)) {
    console.log(`\n❌ Faltan claves en ${lang}:`)
    for (const k of keys) {
      console.log('  -', k, '|', es[k])
    }
  }
  process.exit(2)
}
