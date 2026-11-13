/**
 * AppLangContext — Context de idioma para el back-office
 * 
 * Uso en cualquier componente:
 *   const t = useAppT()
 *   t('projects.title')          → "Proyectos" | "Projects" | ...
 *   t('common.save')             → "Guardar" | "Save" | ...
 *   t('tasks.new_task', 'es')    → fuerza español independientemente
 */
import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react'
import { APP_LANGUAGES, APP_TRANSLATIONS, diccionarioCargado, loadLanguage, respaldoIngles } from './appTranslations.ts'
import { resolveTranslation, getByPath } from './translationRuntime.mjs'

// TODO type: translations come from .mjs runtime with deep dynamic shape; keep loose
type TranslationModule = Record<string, unknown>
type Translations = Record<string, TranslationModule>
type LanguageCustomTranslations = Record<string, TranslationModule>

interface AppLangContextValue {
  lang: string
  setLang: (code: string) => void
  t: (moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>) => string
  translations: Translations
  baseTranslations: Translations
  setCustomTranslations: (data: LanguageCustomTranslations) => void
  customTrans: LanguageCustomTranslations
  loading: boolean
  allTranslations: Record<string, Translations>
}

export const AppLangContext = createContext<AppLangContextValue | null>(null)

export const STORAGE_KEY = 'contecflow_operator_lang'
// Revisión 2026-11: un idioma elegido a mano que aún no ha llegado al servidor
// (p. ej. en la pantalla de entrada). Al cargar las preferencias manda sobre
// el guardado, y se guarda; luego se borra.
export const ELEGIDO_KEY = 'contecflow_lang_elegido'
// Evento que emite `setLang`; lo escucha quien tiene sesión (Layout) y guarda.
export const EVENTO_IDIOMA_ELEGIDO = 'contecflow-lang-elegido'

// Traducciones custom guardadas por el admin (sobreescriben las base)
const CUSTOM_KEY = 'contecflow_custom_translations'

function mergeCustom(base: Translations, custom: TranslationModule | null | undefined): Translations {
  if (!custom || typeof custom !== 'object') return base
  const merged: Translations = { ...base }
  for (const mod of Object.keys(base)) {
    const override = custom[mod]
    merged[mod] = {
      ...base[mod],
      ...(override && typeof override === 'object' && !Array.isArray(override) ? override : {}),
    }
  }
  return merged
}

/**
 * Diccionario del idioma si ya está cargado (el castellano lo está siempre: va
 * en el chunk inicial). En tests no se espera a ninguna descarga —dispararía
 * avisos de act(...)— y se usa el castellano mientras tanto.
 */
function diccionarioInmediato(lang: string, inTest: boolean): Translations | undefined {
  return diccionarioCargado(lang) ?? (inTest ? diccionarioCargado('es') : undefined)
}

function isTestEnvironment(): boolean {
  if (import.meta.env?.VITEST) return true
  if (import.meta.env?.MODE === 'test') return true
  return false
}

export function AppLangProvider({ children }: { children?: ReactNode }) {
  const [lang, setLangState] = useState<string>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return stored
    // Detectar idioma navegador (primer acceso)
    const navLang = (navigator.language || 'es').slice(0,2)
    // 2026-11: `in` sobre un array miraba los índices ("0","1"…), así que siempre caía en 'es'.
    return APP_LANGUAGES.some(l => l.code === navLang) ? navLang : 'es'
  })
  const inTest = isTestEnvironment()

  const [customTrans, setCustomTrans] = useState<LanguageCustomTranslations>(() => {
    try {
      const stored = localStorage.getItem(CUSTOM_KEY)
      return stored ? JSON.parse(stored) : {}
    } catch { return {} }
  })
  // Auditoría 2026-11 (#24a): si el idioma ya está cargado (castellano, o el
  // que se cargó antes) se pinta sin esperar; si no, la aplicación no se monta
  // hasta tenerlo —nunca se ven claves sin traducir—.
  const [baseTranslations, setBaseTranslations] = useState<Translations>(() => diccionarioInmediato(lang, inTest) ?? {})
  const [translations, setTranslations] = useState<Translations>(() => {
    const base = diccionarioInmediato(lang, inTest)
    return base ? mergeCustom(base, customTrans[lang] || {}) : {}
  })
  const [loading, setLoading] = useState<boolean>(() => !diccionarioInmediato(lang, inTest))

  const resolveRawByFullKey = useCallback((fullKey: string): string | undefined => {
    if (!fullKey || typeof fullKey !== 'string' || !fullKey.includes('.')) return undefined
    const parts = fullKey.split('.')
    const moduleName = parts[0]
    const keyPath = parts.slice(1)
    if (!moduleName || keyPath.length === 0) return undefined

    const fallbackKey = keyPath[keyPath.length - 1]
    const candidates = [
      getByPath(translations, moduleName, keyPath),
      getByPath(baseTranslations, moduleName, keyPath),
      getByPath(respaldoIngles(), moduleName, keyPath),
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

  // Idioma activo: inmediato si ya está cargado; si no, se descarga su chunk.
  useEffect(() => {
    const aplicar = (base: Translations) => {
      setBaseTranslations(base)
      setTranslations(mergeCustom(base, customTrans[lang] || {}))
      setLoading(false)
    }
    const inmediato = diccionarioInmediato(lang, inTest)
    if (inmediato) { aplicar(inmediato); return }
    let cancelled = false
    setLoading(true)
    loadLanguage(lang).then(base => { if (!cancelled) aplicar(base) })
    return () => { cancelled = true }
  }, [inTest, lang, customTrans])

  // Revisión 2026-11: este proveedor está por fuera del de sesión, así que el
  // `user` que miraba era siempre null y el idioma no se guardaba nunca. Ahora
  // avisa con un evento y quien tiene sesión lo guarda.
  const setLang = useCallback((code: string) => {
    setLangState(code)
    localStorage.setItem(STORAGE_KEY, code)
    localStorage.setItem(ELEGIDO_KEY, code)
    window.dispatchEvent(new CustomEvent(EVENTO_IDIOMA_ELEGIDO, { detail: { lang: code } }))
  }, [])

  // Escuchar evento de sincronización de idioma (emitido por useUserPreferences
  // al cargar o actualizar prefs del backend)
  useEffect(() => {
    const handler = (e: Event) => {
      const code = (e as CustomEvent<{ lang?: string }>).detail?.lang
      if (code) {
        setLangState(code)
        localStorage.setItem(STORAGE_KEY, code)
      }
    }
    window.addEventListener('contecflow-lang-sync', handler as EventListener)
    return () => window.removeEventListener('contecflow-lang-sync', handler as EventListener)
  }, [])

  const setCustomTranslations = useCallback((data: LanguageCustomTranslations) => {
    setCustomTrans(data)
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(data))
  }, [])

  // Función de traducción:
  //   t('module.key')
  //   t('module', 'key')
  //   t('module.key', { var: value })
  //   t('module.key', 'Fallback')
  const t = useCallback((moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>): string => {
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

    let module: string | undefined
    let keyPath: string[] = []
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
      englishTranslations: respaldoIngles(),
      spanishTranslations: APP_TRANSLATIONS.es,
    })

    // Apply interpolation: replace {varName} placeholders
    if (params && typeof trans === 'string') {
      trans = trans.replace(/\{(\w+)\}/g, (_: string, name: string) =>
        (params as Record<string, unknown>)[name] !== undefined ? String((params as Record<string, unknown>)[name]) : `{${name}}`
      )
    }

    return trans
  }, [translations, baseTranslations, lang, resolveRawByFullKey])

  // Lo cargado hasta ahora; el inglés, entero o solo el respaldo del castellano.
  // (El `value` del proveedor ya se crea en cada render: memorizar esto no ahorra nada.)
  const allTranslations: Record<string, Translations> = { ...APP_TRANSLATIONS, en: respaldoIngles() }

  // Solo se espera a la primera carga. Antes esperaba también al cambiar de
  // idioma: desmontaba la aplicación entera (y con ella el guardado pendiente).
  if (loading && Object.keys(translations).length === 0) return null
  return (
    <AppLangContext.Provider value={{ lang, setLang, t, translations, baseTranslations, setCustomTranslations, customTrans, loading, allTranslations }}>
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
