import { APP_TRANSLATIONS, getAllKeys } from '../src/i18n/todosLosIdiomas.mjs'

const allLanguages = Object.keys(APP_TRANSLATIONS)
const allKeys = getAllKeys()
const missingByLanguage = []

for (const language of allLanguages) {
  const langPack = APP_TRANSLATIONS[language] || {}
  const missing = []

  for (const entry of allKeys) {
    const modulePack = langPack[entry.module] || {}
    if (!(entry.key in modulePack)) {
      missing.push(entry)
    }
  }

  if (missing.length > 0) {
    missingByLanguage.push({
      language,
      missingCount: missing.length,
      sample: missing.slice(0, 15),
    })
  }
}

if (missingByLanguage.length > 0) {
  console.error(JSON.stringify({ ok: false, missingByLanguage }, null, 2))
  process.exit(1)
}

console.log(JSON.stringify({ ok: true, languages: allLanguages.length, keys: allKeys.length }, null, 2))
