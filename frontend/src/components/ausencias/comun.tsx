/**
 * Piezas comunes de las pantallas de ausencias de la persona y de quien aprueba
 * (tarea #25): textos `aus.*`, catálogos (tipos, turnos, tipos de documento) y
 * la etiqueta de estado con su color (sin estilos en línea).
 */
import { useQuery } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaServida, EstadoDeAusencia, TipoDeAusencia } from '../../services/api/tipos-ausencias'
import { STALE_5_MIN_MS } from '../../constants/timings'
import IconoDeAusencia from './IconoDeAusencia'
import { Muestra } from './admin/comun'
import './ausencias.css'

export function useTa() {
  const { t, lang } = useAppLang()
  const ta = (clave: string, params?: Record<string, unknown>) => t(`aus.${clave}`, params)
  return { t, ta, lang }
}

export const useTipos = () =>
  useQuery({ queryKey: ['ausencias', 'tipos'], queryFn: () => ausenciasApi.tipos(), staleTime: STALE_5_MIN_MS })
export const useTurnos = () =>
  useQuery({ queryKey: ['ausencias', 'turnos'], queryFn: () => ausenciasApi.turnos(), staleTime: STALE_5_MIN_MS })
export const useTiposDeDocumento = () =>
  useQuery({ queryKey: ['ausencias', 'documentos'], queryFn: () => ausenciasApi.documentos(), staleTime: STALE_5_MIN_MS })

/** El nombre del tipo en el idioma de la pantalla. */
export function nombreDeTipo(t: Pick<TipoDeAusencia, 'nombre' | 'nombres'>, lang: string): string {
  return t.nombres?.[lang as 'es' | 'en' | 'zh'] || t.nombre
}

export function EstadoDeAusenciaChip({ estado }: { estado: EstadoDeAusencia }) {
  const { ta } = useTa()
  return <span className={`aus-estado aus-estado--${estado}`}>{ta(`estado_${estado}`)}</span>
}

/** El tipo de una ausencia con su color e icono (o «Ausencia» si es privada para quien mira). */
export function TipoChip({ a }: { a: Pick<AusenciaServida, 'type_color' | 'type_icon' | 'type_label' | 'private' | 'absence_type_id'> }) {
  const { ta, lang } = useTa()
  const tipos = useTipos().data ?? []
  const tipo = tipos.find(x => x.id === a.absence_type_id)
  const nombre = a.private ? ta('privada') : tipo ? nombreDeTipo(tipo, lang) : a.type_label
  return (
    <Muestra color={a.type_color} className="aus-tipo">
      <IconoDeAusencia icono={a.type_icon} size={13} />{nombre}
    </Muestra>
  )
}

export function fecha(iso: string | null | undefined, lang: string): string {
  if (!iso) return '—'
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  return d.toLocaleDateString(lang, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function cantidad(a: Pick<AusenciaServida, 'amount' | 'working_days' | 'unit'>, ta: (k: string, p?: Record<string, unknown>) => string): string {
  return ta(`unidad_${a.unit ?? 'dias'}`, { n: a.amount ?? a.working_days ?? 0 })
}
