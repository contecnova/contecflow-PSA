import { mkdirSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'

mkdirSync('reports', { recursive: true })

const eslintJson = spawnSync(
  'npx',
  ['eslint', 'src', '--ext', '.js,.jsx,.ts,.tsx', '--format', 'json'],
  { encoding: 'utf-8' }
)

const stdout = eslintJson.stdout || '[]'
let parsed = []
try {
  parsed = JSON.parse(stdout)
} catch {
  parsed = []
}

const summary = parsed.reduce(
  (acc, file) => {
    acc.files += 1
    for (const msg of file.messages || []) {
      if ((msg.ruleId || '').startsWith('jsx-a11y/')) {
        acc.a11yFindings += 1
        if (msg.severity === 2) acc.a11yErrors += 1
        if (msg.severity === 1) acc.a11yWarnings += 1
      }
    }
    return acc
  },
  { files: 0, a11yFindings: 0, a11yErrors: 0, a11yWarnings: 0 }
)

writeFileSync('reports/a11y-eslint.json', JSON.stringify(parsed, null, 2))
writeFileSync('reports/a11y-summary.json', JSON.stringify(summary, null, 2))

console.log('[a11y-audit] Files scanned:', summary.files)
console.log('[a11y-audit] A11y findings:', summary.a11yFindings)
console.log('[a11y-audit] Errors:', summary.a11yErrors)
console.log('[a11y-audit] Warnings:', summary.a11yWarnings)
console.log('[a11y-audit] Reports: reports/a11y-eslint.json, reports/a11y-summary.json')

if (eslintJson.status !== 0) {
  process.exit(eslintJson.status ?? 1)
}
