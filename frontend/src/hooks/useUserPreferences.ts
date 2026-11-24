/**
 * useUserPreferences — Carga y persiste preferencias de UI del usuario en el backend.
 * Sincroniza accent_color, theme_mode, dashboard_widgets, language, ui_density.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useCallback, useRef } from 'react'
// TODO type: services/api still JS.
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { applyAccent, applyDensity } from '../utils/appearance'
import { ELEGIDO_KEY } from '../i18n/AppLangContext'
// Con extensión: sin ella Vite resuelve a `appTranslations.mjs`, que no la exporta.
import { idiomaDelNavegador } from '../i18n/appTranslations.ts'
import { PREFERENCES_SAVE_DEBOUNCE_MS, STALE_5_MIN_MS } from '../constants/timings'

export type ThemeMode = 'freight' | 'dark' | 'light' | 'high-contrast' | 'midnight' | 'slate' | 'system' | string
export type UIDensity = 'compact' | 'normal' | 'comfortable' | string

export interface UserPreferences {
  dashboard_widgets: unknown
  accent_color: string | null  // vacío: el acento del tema
  theme_mode: ThemeMode
  sidebar_collapsed: boolean
  /** `null`: ni el usuario ni la empresa eligieron (incidencia 5: navegador o inglés). */
  language: string | null
  ui_density: UIDensity
  extra: unknown
  [extra: string]: unknown
}

export interface UseUserPreferencesResult {
  prefs: UserPreferences
  isLoading: boolean
  save: (patch: Partial<UserPreferences>) => void
}

// Defaults
const DEFAULTS: UserPreferences = {
  dashboard_widgets: null,
  accent_color:      null,
  theme_mode:        'freight',
  sidebar_collapsed: false,
  language:          null,
  ui_density:        'normal',
  extra:             null,
}

export function useUserPreferences(): UseUserPreferencesResult {
  const qc = useQueryClient()
  const { user } = useAuth()
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendiente = useRef<Partial<UserPreferences> | null>(null)

  const { data: prefs = DEFAULTS, isLoading } = useQuery<UserPreferences>({
    queryKey: ['user-preferences'],
    queryFn: () => api.get('/users/me/preferences').then((r: { data: UserPreferences }) => r.data).catch(() => DEFAULTS),
    staleTime: STALE_5_MIN_MS,
    enabled: !!user?.id,
  })

  const { mutate: saveMutation } = useMutation({
    mutationFn: (patch: Partial<UserPreferences>) => api.patch('/users/me/preferences', patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['user-preferences'] }),
  })

  // Aplicar accent_color, theme_mode, ui_density al DOM y sincronizar idioma
  // cuando las prefs se cargan desde el backend (útil en dispositivos nuevos)
  useEffect(() => {
    if (!prefs) return
    const root = document.documentElement

    // Idioma — emitir evento para que AppLangContext actualice su estado
    // Se emite siempre (no sólo en discrepancia) para garantizar sincronización
    const elegido = localStorage.getItem(ELEGIDO_KEY)
    if (elegido && prefs !== DEFAULTS) {
      // Elegido a mano sin que llegara al servidor: manda, y se guarda.
      localStorage.removeItem(ELEGIDO_KEY)
      if (elegido !== prefs.language) saveMutation({ language: elegido })
    } else if (prefs !== DEFAULTS) {
      // Incidencia 5 (23-11-2026): preferencia del usuario > idioma de la
      // empresa (los dos vienen en `prefs.language`) > navegador > inglés.
      const lang = prefs.language || idiomaDelNavegador()
      localStorage.setItem('contecflow_operator_lang', lang)
      window.dispatchEvent(new CustomEvent('contecflow-lang-sync', { detail: { lang } }))
    }

    // Accent color (y el texto que va encima, --on-accent)
    applyAccent(prefs.accent_color)  // sin acento propio, el del tema
    // Tema (freight / dark / light / high-contrast / midnight / slate / system)
    const theme = prefs.theme_mode || 'freight'
    if (theme === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      root.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
    } else {
      root.setAttribute('data-theme', theme)
    }
    // Densidad: los tokens que cambia están en index.css ([data-density])
    applyDensity(prefs.ui_density)

  }, [prefs, saveMutation])

  // Guardar con debounce (500ms) para no saturar el backend
  const save = useCallback((patch: Partial<UserPreferences>) => {
    // Actualizar caché inmediatamente (optimistic). 23-11-2026 (menú personalizable):
    // `extra` se fusiona por claves como en el servidor (una clave a null se borra);
    // antes el parche sustituía todo `extra` en la caché hasta volver a leerlo.
    qc.setQueryData(['user-preferences'], (old: UserPreferences | undefined) => {
      const base = old ?? DEFAULTS
      if (!('extra' in patch) || patch.extra === null || typeof patch.extra !== 'object') return { ...base, ...patch }
      const extra: Record<string, unknown> = { ...((base.extra as Record<string, unknown> | null) ?? {}) }
      for (const [k, v] of Object.entries(patch.extra as Record<string, unknown>)) {
        if (v === null) delete extra[k]
        else extra[k] = v
      }
      return { ...base, ...patch, extra }
    })
    // Aplicar cambios CSS inmediatos
    if ('accent_color' in patch) applyAccent(patch.accent_color)
    if (patch.theme_mode) {
      if (patch.theme_mode === 'system') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
        document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
      } else {
        document.documentElement.setAttribute('data-theme', patch.theme_mode)
      }
    }
    if (patch.ui_density) applyDensity(patch.ui_density)
    // Debounce el guardado en backend. 23-11-2026: los parches seguidos se acumulan
    // (antes solo llegaba el último y se perdía, p. ej., el idioma guardado justo antes).
    const previo = pendiente.current
    const extraPrevio = previo?.extra && typeof previo.extra === 'object' ? previo.extra as Record<string, unknown> : null
    const extraNuevo = patch.extra && typeof patch.extra === 'object' ? patch.extra as Record<string, unknown> : null
    pendiente.current = { ...(previo ?? {}), ...patch,
      ...(extraPrevio && extraNuevo ? { extra: { ...extraPrevio, ...extraNuevo } } : {}) }
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      const enviar = pendiente.current
      pendiente.current = null
      if (enviar) saveMutation(enviar)
    }, PREFERENCES_SAVE_DEBOUNCE_MS)
  }, [qc, saveMutation])

  // Cancel pending debounced save on unmount to avoid state updates on unmounted component
  useEffect(() => () => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
  }, [])

  return { prefs, isLoading, save }
}

export default useUserPreferences
