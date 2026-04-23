/**
 * useUserPreferences — Carga y persiste preferencias de UI del usuario en el backend.
 * Sincroniza accent_color, theme_mode, dashboard_widgets, language, ui_density.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useCallback, useRef } from 'react'
import api from '../services/api'

// Defaults
const DEFAULTS = {
  dashboard_widgets: null,
  accent_color:      '#4f8ef7',
  theme_mode:        'dark',
  sidebar_collapsed: false,
  language:          'es',
  ui_density:        'normal',
  extra:             null,
}

export function useUserPreferences() {
  const qc = useQueryClient()
  const saveTimer = useRef(null)

  const { data: prefs = DEFAULTS, isLoading } = useQuery({
    queryKey: ['user-preferences'],
    queryFn: () => api.get('/users/me/preferences').then(r => r.data).catch(() => DEFAULTS),
    staleTime: 5 * 60 * 1000,
  })

  const { mutate: saveMutation } = useMutation({
    mutationFn: (patch) => api.patch('/users/me/preferences', patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['user-preferences'] }),
  })

  // Aplicar accent_color, theme_mode, ui_density al DOM y sincronizar idioma
  // cuando las prefs se cargan desde el backend (útil en dispositivos nuevos)
  useEffect(() => {
    if (!prefs) return
    const root = document.documentElement

    // Idioma — emitir evento para que AppLangContext actualice su estado
    // Se emite siempre (no sólo en discrepancia) para garantizar sincronización
    if (prefs.language) {
      localStorage.setItem('contecflow_operator_lang', prefs.language)
      window.dispatchEvent(new CustomEvent('contecflow-lang-sync', { detail: { lang: prefs.language } }))
    }

    // Accent color
    if (prefs.accent_color) {
      root.style.setProperty('--accent', prefs.accent_color)
      root.style.setProperty('--accent-muted', `${prefs.accent_color}14`)
      root.style.setProperty('--accent-glow',  `${prefs.accent_color}26`)
    }
    // Tema (dark / light / high-contrast / midnight / slate / system)
    const theme = prefs.theme_mode || 'dark'
    if (theme === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      root.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
    } else {
      root.setAttribute('data-theme', theme)
    }
    // Densidad
    const density = prefs.ui_density || 'normal'
    root.setAttribute('data-density', density)
    if (density === 'compact') {
      root.style.setProperty('--space-item', '5px')
      root.style.setProperty('--font-size-base', '12px')
    } else if (density === 'comfortable') {
      root.style.setProperty('--space-item', '10px')
      root.style.setProperty('--font-size-base', '14px')
    } else {
      root.style.setProperty('--space-item', '7px')
      root.style.setProperty('--font-size-base', '13px')
    }
     
  }, [prefs])

  // Guardar con debounce (500ms) para no saturar el backend
  const save = useCallback((patch) => {
    // Actualizar caché inmediatamente (optimistic)
    qc.setQueryData(['user-preferences'], old => ({ ...old, ...patch }))
    // Aplicar cambios CSS inmediatos
    if (patch.accent_color) {
      document.documentElement.style.setProperty('--accent', patch.accent_color)
      document.documentElement.style.setProperty('--accent-muted', `${patch.accent_color}14`)
      document.documentElement.style.setProperty('--accent-glow',  `${patch.accent_color}26`)
    }
    if (patch.theme_mode) {
      document.documentElement.setAttribute('data-theme', patch.theme_mode)
    }
    if (patch.ui_density) {
      const density = patch.ui_density
      document.documentElement.setAttribute('data-density', density)
      const root = document.documentElement
      if (density === 'compact') {
        root.style.setProperty('--space-item', '5px')
        root.style.setProperty('--font-size-base', '12px')
      } else if (density === 'comfortable') {
        root.style.setProperty('--space-item', '10px')
        root.style.setProperty('--font-size-base', '14px')
      } else {
        root.style.setProperty('--space-item', '7px')
        root.style.setProperty('--font-size-base', '13px')
      }
    }
    // Debounce el guardado en backend
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => saveMutation(patch), 500)
  }, [qc, saveMutation])

  // Cancel pending debounced save on unmount to avoid state updates on unmounted component
  useEffect(() => () => clearTimeout(saveTimer.current), [])

  return { prefs, isLoading, save }
}

export default useUserPreferences
