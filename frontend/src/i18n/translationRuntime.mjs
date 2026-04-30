const missingTranslationCache = new Set()

function isObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value)
}

export function deepMergeTranslations(base, override) {
  if (!isObject(base)) return isObject(override) ? { ...override } : override
  if (!isObject(override)) return { ...base }

  const result = { ...base }
  for (const [key, overrideValue] of Object.entries(override)) {
    const baseValue = result[key]
    if (isObject(baseValue) && isObject(overrideValue)) {
      result[key] = deepMergeTranslations(baseValue, overrideValue)
      continue
    }
    result[key] = overrideValue
  }
  return result
}

export function getByPath(source, moduleName, keyPath) {
  if (!source || typeof source !== 'object') return undefined
  let current = source[moduleName]
  for (const part of keyPath) {
    if (current == null) return undefined
    current = current[part]
  }
  return current
}

export function humanizeFallbackKey(rawKey) {
  const clean = String(rawKey || '').trim()
  if (!clean) return ''
  const spaced = clean
    .replace(/[_.-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!spaced) return clean
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function reportMissingTranslation({ lang, fullKey, source }) {
  const mode = typeof import.meta !== 'undefined' ? import.meta.env?.MODE : undefined
  const shouldLog = mode === 'development' || mode === 'test'
  if (!shouldLog) return

  const cacheKey = `${lang}::${fullKey}`
  if (missingTranslationCache.has(cacheKey)) return
  missingTranslationCache.add(cacheKey)

  // Keep warning concise and deduplicated to avoid console noise.
  globalThis.console?.warn?.(`[i18n-missing] ${fullKey} (lang=${lang}, source=${source})`)
}

export function resolveTranslation({
  lang,
  moduleName,
  keyPath,
  runtimeTranslations,
  baseTranslations,
  englishTranslations,
  spanishTranslations,
}) {
  const fallbackKey = keyPath[keyPath.length - 1] || `${moduleName}`
  const fullKey = `${moduleName}.${keyPath.join('.')}`

  const candidates = [
    ['runtime', getByPath(runtimeTranslations, moduleName, keyPath)],
    ['base', getByPath(baseTranslations, moduleName, keyPath)],
    ['english', getByPath(englishTranslations, moduleName, keyPath)],
    ['spanish', getByPath(spanishTranslations, moduleName, keyPath)],
  ]

  for (const [source, value] of candidates) {
    if (typeof value !== 'string') continue
    if (value === fallbackKey) continue
    if (!value.trim()) continue
    return value
  }

  reportMissingTranslation({ lang, fullKey, source: 'humanized' })
  return humanizeFallbackKey(fallbackKey)
}
