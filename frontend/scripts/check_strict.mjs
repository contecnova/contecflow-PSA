#!/usr/bin/env node
/**
 * check_strict.mjs — Audit #C9 helper.
 *
 * Runs `tsc --noEmit -p tsconfig.strict.json` and filters the output so that
 * only errors located in files listed under `include` count toward the exit
 * code. TypeScript will still LOAD non-include files (it has to, to resolve
 * imports), but their errors are not the responsibility of this gate — they
 * belong to the gradual migration of @ts-nocheck files.
 *
 * Usage:
 *   node scripts/check_strict.mjs           # CI gate
 */
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const cfgPath = resolve('tsconfig.strict.json')
// Naive include extraction — we only need the file paths; using JSON.parse
// would require stripping the leading "//xx" pseudo-comment keys.
const raw = readFileSync(cfgPath, 'utf-8')
const includeMatch = raw.match(/"include"\s*:\s*\[([\s\S]*?)\]/)
const whitelist = includeMatch
  ? [...includeMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1].replace(/\\/g, '/'))
  : []

if (whitelist.length === 0) {
  console.log('check_strict: whitelist empty, nothing to check.')
  process.exit(0)
}

const tsc = spawnSync('node', ['node_modules/typescript/bin/tsc', '--noEmit', '-p', 'tsconfig.strict.json'], {
  encoding: 'utf-8',
})

const lines = (tsc.stdout || '').split('\n')
const offenders = lines.filter((line) => {
  // Match lines like "src/foo.ts(12,3): error TS1234"
  const m = line.match(/^([^()]+)\(\d+,\d+\): error /)
  if (!m) return false
  const file = m[1].replace(/\\/g, '/')
  return whitelist.some((w) => file === w || file.endsWith('/' + w))
})

const totalOutput = (tsc.stdout || '').match(/error /g)?.length || 0
console.log(`check_strict: ${offenders.length} error(s) in ${whitelist.length} whitelisted file(s).`)
console.log(`check_strict: (${totalOutput - offenders.length} additional errors in non-whitelisted files were ignored — those belong to the gradual @ts-nocheck migration.)`)

if (offenders.length > 0) {
  console.error('\nErrors in whitelisted files:')
  for (const line of offenders) console.error('  ' + line)
  process.exit(1)
}
process.exit(0)
