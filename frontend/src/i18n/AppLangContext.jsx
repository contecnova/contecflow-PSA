/**
 * AppLangContext — Context de idioma para el back-office
 * 
 * Uso en cualquier componente:
 *   const t = useAppT()
 *   t('projects.title')          → "Proyectos" | "Projects" | ...
 *   t('common.save')             → "Guardar" | "Save" | ...
 *   t('tasks.new_task', 'es')    → fuerza español independientemente
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { AuthContext } from '../context/AuthContext'
import { APP_LANGUAGES, APP_TRANSLATIONS, loadLanguage } from './appTranslations'
import { deepMergeTranslations, resolveTranslation, getByPath } from './translationRuntime.mjs'
import api from '../services/api'

export const AppLangContext = createContext(null)

export const STORAGE_KEY = 'contecflow_operator_lang'

// Traducciones custom guardadas por el admin (sobreescriben las base)
const CUSTOM_KEY = 'contecflow_custom_translations'

function mergeCustom(base, custom) {
  if (!custom || typeof custom !== 'object') return base
  const merged = { ...base }
  for (const mod of Object.keys(base)) {
    merged[mod] = {
      ...base[mod],
      ...(custom[mod] || {}),
    }
  }
  return merged
}

function mergeWithEnglishFallback(targetLang) {
  const safeLang = APP_TRANSLATIONS[targetLang] ? targetLang : 'es'
  const target = APP_TRANSLATIONS[safeLang] || APP_TRANSLATIONS.es || {}
  if (safeLang === 'en') return target
  const english = APP_TRANSLATIONS.en || target
  return deepMergeTranslations(english, target)
}

function isTestEnvironment() {
  if (typeof process !== 'undefined' && process.env?.VITEST) return true
  if (typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'test') return true
  return false
}

export function AppLangProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return stored
    // Detectar idioma navegador (primer acceso)
    const navLang = (navigator.language || 'es').slice(0,2)
    return navLang in APP_LANGUAGES ? navLang : 'es'
  })
  // Auth es opcional aquí para evitar dependencia circular de providers en bootstrap.
  const auth = useContext(AuthContext)
  const user = auth?.user ?? null
  const inTest = isTestEnvironment()

  const [customTrans, setCustomTrans] = useState(() => {
    try {
      const stored = localStorage.getItem(CUSTOM_KEY)
      return stored ? JSON.parse(stored) : {}
    } catch { return {} }
  })
  const [baseTranslations, setBaseTranslations] = useState(() => inTest ? mergeWithEnglishFallback(lang) : {})
  const [translations, setTranslations] = useState(() => {
    if (!inTest) return {}
    const base = mergeWithEnglishFallback(lang)
    const custom = customTrans[lang] || {}
    return mergeCustom(base, custom)
  })
  const [loading, setLoading] = useState(() => !inTest)

  const resolveRawByFullKey = useCallback((fullKey) => {
    if (!fullKey || typeof fullKey !== 'string' || !fullKey.includes('.')) return undefined
    const parts = fullKey.split('.')
    const moduleName = parts[0]
    const keyPath = parts.slice(1)
    if (!moduleName || keyPath.length === 0) return undefined

    const fallbackKey = keyPath[keyPath.length - 1]
    const candidates = [
      getByPath(translations, moduleName, keyPath),
      getByPath(baseTranslations, moduleName, keyPath),
      getByPath(APP_TRANSLATIONS.en, moduleName, keyPath),
      getByPath(APP_TRANSLATIONS.es, moduleName, keyPath),
    ]

    for (const value of candidates) {
      if (typeof value !== 'string') continue
      if (!value.trim()) continue
      if (value === fallbackKey) continue
      return value
    }
    return undefined
  }, [translations, baseTranslations])

  // Carga asíncrona del idioma activo
  useEffect(() => {
    if (inTest) return
    let cancelled = false
    setLoading(true)
    loadLanguage(lang).then(base => {
      if (!cancelled) {
        setBaseTranslations(base)
        const custom = customTrans[lang] || {}
        setTranslations(mergeCustom(base, custom))
        setLoading(false)
      }
    })
    return () => { cancelled = true }
     
  }, [inTest, lang, customTrans])

  // En tests evitamos carga async para no disparar warnings de act(...)
  useEffect(() => {
    if (!inTest) return
    const base = mergeWithEnglishFallback(lang)
    const custom = customTrans[lang] || {}
    setBaseTranslations(base)
    setTranslations(mergeCustom(base, custom))
    setLoading(false)
  }, [inTest, lang, customTrans])

  const setLang = useCallback((code) => {
    setLangState(code)
    localStorage.setItem(STORAGE_KEY, code)
    // Solo persistir en backend si hay usuario autenticado
    if (user) {
      api.patch('/users/me/preferences', { language: code }).catch(() => {})
    }
  }, [user])

  // Escuchar evento de sincronización de idioma (emitido por useUserPreferences
  // al cargar o actualizar prefs del backend)
  useEffect(() => {
    const handler = (e) => {
      const code = e.detail?.lang
      if (code) {
        setLangState(code)
        localStorage.setItem(STORAGE_KEY, code)
      }
    }
    window.addEventListener('contecflow-lang-sync', handler)
    return () => window.removeEventListener('contecflow-lang-sync', handler)
  }, [])

  const setCustomTranslations = useCallback((data) => {
    setCustomTrans(data)
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(data))
  }, [])

  // Función de traducción:
  //   t('module.key')
  //   t('module', 'key')
  //   t('module.key', { var: value })
  //   t('module.key', 'Fallback')
  const t = useCallback((moduleOrFullKey, keyOrParams) => {
    // Detect if second argument is an interpolation params object
    const isParams = keyOrParams !== null
      && typeof keyOrParams === 'object'
      && !Array.isArray(keyOrParams)
    const params = isParams ? keyOrParams : null
    const fallback = !isParams && typeof keyOrParams === 'string' ? keyOrParams : undefined

    // Backward-compatible shorthand: t('module.key', 'Fallback text')
    // If first arg already contains a full key path, treat second string as
    // literal fallback instead of subkey to avoid synthetic i18n-missing keys.
    if (!isParams && fallback && typeof moduleOrFullKey === 'string' && moduleOrFullKey.includes('.')) {
      const existing = resolveRawByFullKey(moduleOrFullKey)
      if (existing) return existing
      return fallback
    }

    const key = isParams ? undefined : keyOrParams

    let module
    let keyPath = []
    if (key) {
      module = moduleOrFullKey
      keyPath = String(key).split('.')
    } else if (moduleOrFullKey.includes('.')) {
      const parts = moduleOrFullKey.split('.')
      module = parts[0]
      keyPath = parts.slice(1)
    } else {
      return moduleOrFullKey // fallback: devolver la clave tal cual
    }

    let trans = resolveTranslation({
      lang,
      moduleName: module,
      keyPath,
      runtimeTranslations: translations,
      baseTranslations,
      englishTranslations: APP_TRANSLATIONS.en,
      spanishTranslations: APP_TRANSLATIONS.es,
    })

    // Apply interpolation: replace {varName} placeholders
    if (params && typeof trans === 'string') {
      trans = trans.replace(/\{(\w+)\}/g, (_, name) =>
        params[name] !== undefined ? params[name] : `{${name}}`
      )
    }

    return trans
  }, [translations, baseTranslations, lang, resolveRawByFullKey])

  if (loading) return null // O un spinner global
  return (
    <AppLangContext.Provider value={{ lang, setLang, t, translations, baseTranslations, setCustomTranslations, customTrans, loading, allTranslations: APP_TRANSLATIONS }}>
      {children}
    </AppLangContext.Provider>
  )
}

export function useAppLang() {
  const ctx = useContext(AppLangContext)
  if (!ctx) throw new Error('useAppLang debe usarse dentro de AppLangProvider')
  return ctx
}

/** Hook corto: const t = useAppT() */
export function useAppT() {
  return useAppLang().t
}

export default AppLangContext
