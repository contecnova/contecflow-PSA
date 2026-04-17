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
import { APP_TRANSLATIONS, APP_LANGUAGES } from './appTranslations'
import api from '../services/api'

const AppLangContext = createContext(null)

export const STORAGE_KEY = 'clarive_operator_lang'

// Traducciones custom guardadas por el admin (sobreescriben las base)
const CUSTOM_KEY = 'clarive_custom_translations'

function mergeCustom(base, custom) {
  if (!custom || typeof custom !== 'object') return base
  const merged = {}
  for (const lang of Object.keys(base)) {
    merged[lang] = {}
    for (const mod of Object.keys(base[lang])) {
      merged[lang][mod] = {
        ...base[lang][mod],
        ...(custom[lang]?.[mod] || {}),
      }
    }
  }
  return merged
}

export function AppLangProvider({ children }) {
  const [lang, setLangState] = useState(
    () => localStorage.getItem(STORAGE_KEY) || 'es'
  )
  const [customTrans, setCustomTrans] = useState(() => {
    try {
      const stored = localStorage.getItem(CUSTOM_KEY)
      return stored ? JSON.parse(stored) : {}
    } catch { return {} }
  })

  const translations = mergeCustom(APP_TRANSLATIONS, customTrans)

  const setLang = useCallback((code) => {
    setLangState(code)
    localStorage.setItem(STORAGE_KEY, code)
    // Persist language preference in backend; local state remains source of truth on failures.
    api.patch('/users/me/preferences', { language: code }).catch(() => {})
  }, [])

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
    window.addEventListener('clarive-lang-sync', handler)
    return () => window.removeEventListener('clarive-lang-sync', handler)
  }, [])

  const setCustomTranslations = useCallback((data) => {
    setCustomTrans(data)
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(data))
  }, [])

  // Función de traducción: t('module.key') o t('module', 'key')
  // Soporta interpolación: t('module.key', { var1: val1, var2: val2 })
  const t = useCallback((moduleOrFullKey, keyOrLangOrParams, forceLang) => {
    // Detect if second argument is an interpolation params object
    const isParams = keyOrLangOrParams !== null
      && typeof keyOrLangOrParams === 'object'
      && !Array.isArray(keyOrLangOrParams)
    const params = isParams ? keyOrLangOrParams : null
    const keyOrLang = isParams ? undefined : keyOrLangOrParams

    const activeLang = forceLang || lang
    let module, key
    if (keyOrLang && !APP_LANGUAGES.find(l => l.code === keyOrLang)) {
      module = moduleOrFullKey
      key    = keyOrLang
    } else if (moduleOrFullKey.includes('.')) {
      [module, key] = moduleOrFullKey.split('.', 2)
    } else {
      return moduleOrFullKey // fallback: devolver la clave tal cual
    }

    let trans = translations[activeLang]?.[module]?.[key]
           || translations['es']?.[module]?.[key]
           || translations['en']?.[module]?.[key]
           || key

    // Apply interpolation: replace {varName} placeholders
    if (params && typeof trans === 'string') {
      trans = trans.replace(/\{(\w+)\}/g, (_, name) =>
        params[name] !== undefined ? params[name] : `{${name}}`
      )
    }

    return trans
  }, [lang, translations])

  return (
    <AppLangContext.Provider value={{ lang, setLang, t, translations, setCustomTranslations, customTrans }}>
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
