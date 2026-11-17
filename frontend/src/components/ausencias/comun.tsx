/**
 * Piezas comunes de las pantallas de ausencias de la persona y de quien aprueba
 * (tarea #25): textos `aus.*`, catálogos (tipos, turnos, tipos de documento) y
 * la etiqueta de estado con su color (sin estilos en línea).
 */
import { fmtDate, fmtNumber } from '../../utils/helpers'
import { useQuery } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaServida, EstadoDeAusencia, ModoDePeticion, TipoDeAusencia, Tramo, Turno } from '../../services/api/tipos-ausencias'
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

export function fecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  // Fecha local (sin desplazarse por zona horaria) con el formateador de la app.
  return fmtDate(new Date(`${iso.slice(0, 10)}T00:00:00`))
}

export function cantidad(
  a: Pick<AusenciaServida, 'amount' | 'working_days' | 'unit'> & Partial<Pick<AusenciaServida, 'modo' | 'start_time' | 'end_time'>>,
  ta: (k: string, p?: Record<string, unknown>) => string,
): string {
  const base = ta(`unidad_${a.unit ?? 'dias'}`, { n: num(a.amount ?? a.working_days ?? 0) })
  return a.modo === 'horas' && a.start_time && a.end_time ? `${base} · ${a.start_time}–${a.end_time}` : base
}

/** Un número con hasta dos decimales en el formato del idioma (0,25 días; 1,5 h). */
export function num(n: number | null | undefined): string {
  return fmtNumber(n ?? 0, 2)
}

/** Franjas como texto: «09:00–14:00, 16:00–19:00». */
export function textoDeTramos(tramos: Tramo[] | null | undefined): string {
  return (tramos ?? []).map(([a, b]) => `${a}–${b}`).join(', ')
}

/** Los tramos de un turno (los antiguos solo traen inicio y fin). */
export function tramosDe(t: Pick<Turno, 'tramos' | 'hora_inicio' | 'hora_fin'>): Tramo[] {
  return t.tramos?.length ? t.tramos.map(([a, b]) => [a, b] as Tramo) : [[t.hora_inicio, t.hora_fin]]
}

/** Minutos de 'HH:MM'. */
export function minutosDe(h: string): number {
  const [a, b] = h.split(':').map(Number)
  return (a || 0) * 60 + (b || 0)
}

/** Horas que suman unas franjas (cada una puede cruzar la medianoche) menos la pausa. */
export function horasDeTramos(tramos: Tramo[], pausaMinutos = 0): { horas: number; cruza: boolean } {
  let total = 0
  let cruza = false
  for (const [a, b] of tramos) {
    if (!a || !b) continue
    const d = minutosDe(b) - minutosDe(a)
    if (d <= 0) cruza = true
    total += d <= 0 ? d + 1440 : d
  }
  return { horas: Math.round((Math.max(0, total - pausaMinutos) / 60) * 100) / 100, cruza }
}

/** Los modos en que se puede pedir un tipo; sin `modos` (tipos antiguos), según su unidad. */
export function modosDeTipo(t: Pick<TipoDeAusencia, 'modos' | 'unidad'> | undefined): ModoDePeticion[] {
  if (!t) return ['dias']
  if (t.modos?.length) return t.modos
  return t.unidad === 'horas' ? ['horas'] : t.unidad === 'medios_dias' ? ['dias', 'medio_dia'] : ['dias', 'medio_dia']
}
