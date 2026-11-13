import fs from 'node:fs'
import path from 'node:path'
import { APP_TRANSLATIONS, getAllKeys } from '../src/i18n/todosLosIdiomas.mjs'

const baselinePath = path.resolve(process.cwd(), 'scripts/i18n_baseline.json')

function loadBaseline() {
  if (!fs.existsSync(baselinePath)) {
    throw new Error(`Missing baseline file: ${baselinePath}`)
  }
  return JSON.parse(fs.readFileSync(baselinePath, 'utf8'))
}

function computeMissingByLanguage() {
  const allLanguages = Object.keys(APP_TRANSLATIONS)
  const allKeys = getAllKeys()
  const perLanguage = {}

  for (const language of allLanguages) {
    const langPack = APP_TRANSLATIONS[language] || {}
    let missingCount = 0

    for (const entry of allKeys) {
      const modulePack = langPack[entry.module] || {}
      if (!(entry.key in modulePack)) {
        missingCount += 1
      }
    }

    perLanguage[language] = missingCount
  }

  return {
    totalKeys: allKeys.length,
    perLanguage,
  }
}

const baseline = loadBaseline()
const current = computeMissingByLanguage()
const regressions = []

for (const [lang, currentCount] of Object.entries(current.perLanguage)) {
  const baselineCount = Number(baseline?.perLanguage?.[lang] ?? 0)
  if (currentCount > baselineCount) {
    regressions.push({
      language: lang,
      baselineCount,
      currentCount,
      delta: currentCount - baselineCount,
    })
  }
}

if (regressions.length > 0) {
  console.error(
    JSON.stringify(
      {
        ok: false,
        reason: 'i18n debt regression detected',
        baselineTotalKeys: baseline.totalKeys,
        currentTotalKeys: current.totalKeys,
        regressions,
      },
      null,
      2,
    ),
  )
  process.exit(1)
}

console.log(
  JSON.stringify(
    {
      ok: true,
      message: 'No i18n debt regression',
      baselineTotalKeys: baseline.totalKeys,
      currentTotalKeys: current.totalKeys,
      perLanguage: current.perLanguage,
    },
    null,
    2,
  ),
)
