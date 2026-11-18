/**
 * Piezas comunes de la pantalla de horas extra (18-11-2026): textos `hext.*`,
 * configuración compartida, formato de fechas y horas, estado con su tono,
 * avisos y errores traducidos (`extractErr` → `err_srv.*`).
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Ban, Info } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr, fmtDate, fmtDateTime, fmtNumber } from '../../utils/helpers'
import { STALE_5_MIN_MS } from '../../constants/timings'
import { horasExtraApi, type ConfigHe, type EstadoHe, type PeticionHe } from '../../services/api/horas-extra'
import { StatusBadge, type StatusBadgeKind } from '../ui'
import type { NivelDeConsumo } from './logica'
import './horas-extra.css'

export type Th = (clave: string, params?: Record<string, unknown>) => string

export function useTh() {
  const { t, lang } = useAppLang()
  const th: Th = (clave, params) => t(`hext.${clave}`, params)
  return { t, th, lang }
}

/** Sin configuración (o sin el módulo en el servidor) la pantalla funciona con los valores por defecto: desactivado. */
export const CONFIG_HE_POR_DEFECTO: ConfigHe = {
  activo: true, control_imputacion: 'avisar', tolerancia_minutos: 15, compensaciones: ['pago', 'bolsa', 'ninguna'],
  compensacion_por_defecto: 'bolsa', workflow_id: null, tipo_bolsa_id: null, pedir_en_nombre: true, exigir_motivo: true,
  updated_at: null, updated_by: null, puede_editar: false, flujos: [], tipos_de_bolsa: [],
}

/** La configuración, una sola petición: sin reintentos ni refrescos al enfocar; un error (404 incluido)
 *  se queda en los valores por defecto sin repetir la llamada. `enabled` para no pedirla donde no hace falta. */
export const useConfigHe = (enabled = true) =>
  useQuery({
    queryKey: ['horas-extra', 'config'],
    queryFn: () => horasExtraApi.config().catch(() => CONFIG_HE_POR_DEFECTO),
    staleTime: STALE_5_MIN_MS, retry: false, refetchOnWindowFocus: false, enabled,
  })

/** Un valor que cambia sin pausa se lee cuando lleva `ms` quieto (vista previa en vivo). */
export function useRetrasado<T>(valor: T, ms: number): T {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const id = window.setTimeout(() => setV(valor), ms)
    return () => window.clearTimeout(id)
  }, [valor, ms])
  return v
}

export function fecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  return fmtDate(new Date(`${iso.slice(0, 10)}T00:00:00`))
}
export const fechaHora = (iso: string | null | undefined): string => (iso ? fmtDateTime(iso) : '—')
/** Horas con hasta dos decimales en el formato del idioma: «1,5 h». */
export const horas = (n: number | null | undefined): string => (n === null || n === undefined ? '—' : `${fmtNumber(n, 2)} h`)
export const franja = (p: Pick<PeticionHe, 'hora_inicio' | 'hora_fin'>): string =>
  p.hora_inicio && p.hora_fin ? `${p.hora_inicio}–${p.hora_fin}` : '—'
export const textoDeTramos = (tramos: Array<[string, string]> | null | undefined): string =>
  (tramos ?? []).map(([a, b]) => `${a}–${b}`).join(', ') || '—'

export const TONO_DE_ESTADO: Record<EstadoHe, StatusBadgeKind> = {
  pendiente: 'warning', aprobada: 'success', rechazada: 'danger', cancelada: 'neutral',
}
export const TONO_DE_NIVEL: Record<NivelDeConsumo, StatusBadgeKind> = { ok: 'success', atencion: 'warning', excedido: 'danger' }

export function EstadoHeBadge({ p }: { p: Pick<PeticionHe, 'estado' | 'liquidacion'> }) {
  const { th } = useTh()
  return (
    <span className="hext-fila">
      <StatusBadge kind={TONO_DE_ESTADO[p.estado] ?? 'neutral'}>{th(`estado_${p.estado}`)}</StatusBadge>
      {p.liquidacion && <StatusBadge kind="info">{th('liquidada')}</StatusBadge>}
    </span>
  )
}

/** Aviso en línea (atención, bloqueo o información) con su icono. */
export function Aviso({ tono, children }: { tono: 'aviso' | 'bloqueo' | 'info'; children: ReactNode }) {
  const Icono = tono === 'bloqueo' ? Ban : tono === 'aviso' ? AlertTriangle : Info
  return (
    <p className={`hext-aviso hext-aviso--${tono}`} role={tono === 'bloqueo' ? 'alert' : 'status'}>
      <Icono size={13} aria-hidden />{children}
    </p>
  )
}

/** El error de una llamada, traducido si trae código del servidor. */
export function AvisoDeError({ error }: { error: unknown }) {
  const { th } = useTh()
  if (!error) return null
  return <Aviso tono="bloqueo">{extractErr(error, th('error'))}</Aviso>
}

/** Pares etiqueta / valor (los vacíos no se pintan). */
export function Datos({ filas }: { filas: Array<[ReactNode, ReactNode] | null | false> }) {
  const visibles = filas.filter((f): f is [ReactNode, ReactNode] => Boolean(f))
  if (!visibles.length) return null
  return (
    <dl className="hext-datos">
      {visibles.map(([k, v], i) => <div key={i} className="hext-dato"><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}
