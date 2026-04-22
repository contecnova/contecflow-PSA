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
import { useAuth } from '../context/AuthContext'
import { APP_LANGUAGES, loadLanguage } from './appTranslations'
import api from '../services/api'

export const AppLangContext = createContext(null)

export const STORAGE_KEY = 'clarive_operator_lang'

// Traducciones custom guardadas por el admin (sobreescriben las base)
const CUSTOM_KEY = 'clarive_custom_translations'

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

export function AppLangProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return stored
    // Detectar idioma navegador (primer acceso)
    const navLang = (navigator.language || 'es').slice(0,2)
    return navLang in APP_LANGUAGES ? navLang : 'es'
  })
  // Obtener usuario autenticado
  const { user } = useAuth ? useAuth() : { user: null }

  const [customTrans, setCustomTrans] = useState(() => {
    try {
      const stored = localStorage.getItem(CUSTOM_KEY)
      return stored ? JSON.parse(stored) : {}
    } catch { return {} }
  })
  const [translations, setTranslations] = useState({})
  const [loading, setLoading] = useState(true)

  // Carga asíncrona del idioma activo
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadLanguage(lang).then(base => {
      if (!cancelled) {
        const custom = customTrans[lang] || {}
        setTranslations(mergeCustom(base, custom))
        setLoading(false)
      }
    })
    return () => { cancelled = true }
    // eslint-disable-next-line
  }, [lang, customTrans])

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
    window.addEventListener('clarive-lang-sync', handler)
    return () => window.removeEventListener('clarive-lang-sync', handler)
  }, [])

  const setCustomTranslations = useCallback((data) => {
    setCustomTrans(data)
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(data))
  }, [])

  // Función de traducción: t('module.key') o t('module', 'key')
  // Soporta claves anidadas: t('module.section.key')
  // Soporta interpolación: t('module.key', { var1: val1, var2: val2 })
  const t = useCallback((moduleOrFullKey, keyOrParams) => {
    // Detect if second argument is an interpolation params object
    const isParams = keyOrParams !== null
      && typeof keyOrParams === 'object'
      && !Array.isArray(keyOrParams)
    const params = isParams ? keyOrParams : null
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

    let trans = translations?.[module]
    for (const part of keyPath) {
      if (trans == null) break
      trans = trans[part]
    }

    const fallbackKey = keyPath[keyPath.length - 1] || moduleOrFullKey
    if (trans == null) trans = fallbackKey // fallback: clave

    // Apply interpolation: replace {varName} placeholders
    if (params && typeof trans === 'string') {
      trans = trans.replace(/\{(\w+)\}/g, (_, name) =>
        params[name] !== undefined ? params[name] : `{${name}}`
      )
    }

    return trans
  }, [translations])

  if (loading) return null // O un spinner global
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
