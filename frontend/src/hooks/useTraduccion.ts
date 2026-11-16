/**
 * useTraduccion — traducción en tiempo real (16-11-2026).
 *
 * - `useConfigDeTraduccion()`: si la empresa traduce, proveedor, canales e idiomas.
 * - `useMensajesTraducidos(items)`: los mensajes en el idioma de la interfaz de quien
 *   mira. Una sola petición por pantalla; el servidor devuelve lo ya guardado o traduce
 *   (y guarda) lo que falta. Clave de caché por ids + idioma: dos operadores con idiomas
 *   distintos piden cada uno el suyo.
 * - `nombreDeIdioma(codigo, idiomaDeLaInterfaz)`: nombre del idioma en el idioma de
 *   quien mira (`Intl.DisplayNames`), nunca una tabla fija.
 * - `motivoDeTraduccion(t, codigo)` y `errorDeTraduccion(t, detalle)`: códigos del
 *   servidor (`reason`, `trad_*`) traducidos.
 */
import { useMemo } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useAppLang } from '../i18n/AppLangContext'
import { traduccionApi, type MensajeTraducido, type TipoDeMensaje } from '../services/api/traduccion'

/** Cuánto se reutiliza la configuración antes de volver a pedirla (ms). */
const CONFIG_STALE_MS = 60_000

export function useConfigDeTraduccion() {
  return useQuery({ queryKey: ['traduccion-config'], queryFn: traduccionApi.config, staleTime: CONFIG_STALE_MS })
}

export interface ElementoATraducir { type: TipoDeMensaje; id: string }

/** Clave de un resultado: `tipo:id:campo`. */
export function claveDeTraduccion(type: string, id: string, field = 'body'): string {
  return `${type}:${id}:${field}`
}

/**
 * Los mensajes en el idioma de la interfaz. Solo pide si la empresa traduce o hay
 * versiones del autor guardadas (el servidor lo resuelve): con `activo=false` no pide nada.
 */
export function useMensajesTraducidos(items: ElementoATraducir[], activo = true) {
  const { lang } = useAppLang()
  const ids = useMemo(() => items.map(i => `${i.type}:${i.id}`).sort(), [items])
  const consulta = useQuery({
    queryKey: ['traduccion-mensajes', lang, ids],
    queryFn: () => traduccionApi.mensajes(items, lang),
    enabled: activo && items.length > 0,
    staleTime: Infinity,
    // Al llegar un mensaje nuevo la clave cambia: lo ya traducido no vuelve al original mientras tanto.
    placeholderData: keepPreviousData,
  })
  const porClave = useMemo(() => {
    const m = new Map<string, MensajeTraducido>()
    for (const it of consulta.data?.items ?? []) m.set(claveDeTraduccion(it.type, it.id, it.field), it)
    return m
  }, [consulta.data])
  return { ...consulta, porClave, idioma: lang }
}

export function nombreDeIdioma(codigo: string | null | undefined, idiomaDeLaInterfaz: string): string {
  if (!codigo) return ''
  try {
    const nombres = new Intl.DisplayNames([idiomaDeLaInterfaz], { type: 'language' })
    return nombres.of(codigo === 'zh-hant' ? 'zh-Hant' : codigo) ?? codigo
  } catch {
    return codigo
  }
}

type T = (clave: string, respaldo?: string | Record<string, unknown>) => string

export function motivoDeTraduccion(t: T, codigo: string | null | undefined): string {
  if (!codigo) return t('traduccion.motivo.provider_error')
  return t(`traduccion.motivo.${codigo}`, t('traduccion.motivo.provider_error'))
}

export function errorDeTraduccion(t: T, detalle: string): string {
  if (detalle.startsWith('trad_')) return t(`traduccion.err.${detalle.slice('trad_'.length)}`, t('traduccion.err.generico'))
  return detalle || t('traduccion.err.generico')
}
