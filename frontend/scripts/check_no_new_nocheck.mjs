#!/usr/bin/env node
/**
 * check_no_new_nocheck.mjs — ratchet gate for the @ts-nocheck eradication ramp.
 *
 * Counts `// @ts-nocheck` files under src/ and fails if the count EXCEEDS the
 * recorded baseline (scripts/nocheck_baseline.json). New code may never add a
 * @ts-nocheck; as files are strict-cleaned the baseline only ratchets DOWN.
 *
 * Usage:
 *   node scripts/check_no_new_nocheck.mjs          # CI gate
 *   node scripts/check_no_new_nocheck.mjs --update # re-baseline after cleaning files
 */
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'

const SRC = resolve('src')
const BASELINE = resolve('scripts/nocheck_baseline.json')

function walk(dir) {
  let out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) out = out.concat(walk(p))
    else if (/\.(ts|tsx)$/.test(name)) out.push(p)
  }
  return out
}

const files = walk(SRC).filter(f => readFileSync(f, 'utf8').includes('@ts-nocheck'))
const count = files.length

if (process.argv.includes('--update')) {
  writeFileSync(BASELINE, JSON.stringify({ count }, null, 2) + '\n')
  console.log(`[no-new-nocheck] baseline updated → ${count}`)
  process.exit(0)
}

const baseline = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')).count : Infinity
if (count > baseline) {
  console.error(`[no-new-nocheck] FAIL: ${count} @ts-nocheck files > baseline ${baseline}. New @ts-nocheck is not allowed; remove it and fix the types.`)
  process.exit(1)
}
console.log(`[no-new-nocheck] OK: ${count} @ts-nocheck files (baseline ${baseline}).`)
