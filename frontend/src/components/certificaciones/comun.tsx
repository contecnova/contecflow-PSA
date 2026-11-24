/**
 * Certificaciones (migración 212, docs/CERTIFICACIONES.md): piezas comunes de las pestañas.
 */
import { StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import type { EstadoMatriz } from '../../services/api/certificaciones'
import './Certificaciones.css'

export const ESTADOS_MATRIZ: EstadoMatriz[] = ['cumple', 'en_curso', 'pendiente', 'no_cumple', 'caducado', 'no_aplica']

const TONO: Record<string, StatusBadgeKind> = {
  cumple: 'success', en_curso: 'accent', pendiente: 'neutral', no_cumple: 'danger', caducado: 'orange',
  no_aplica: 'neutral', valida: 'success', caducada: 'orange', pendiente_aprobacion: 'warning',
  eficaz: 'success', parcial: 'warning', no_eficaz: 'danger', sin_evaluar: 'neutral', implantado: 'success',
  abierto: 'warning', en_correccion: 'accent', corregido: 'info', cerrado: 'success', abierta: 'warning',
  hecha: 'info', verificada: 'success', vigente: 'success', suspendido: 'warning', retirado: 'neutral',
  caducado_cert: 'danger', cumplido: 'success', tarde: 'orange', vencido: 'danger', nc_mayor: 'danger',
  nc_menor: 'orange', observacion: 'warning', oportunidad: 'info', planificada: 'neutral', informe: 'warning',
  cerrada: 'success', borrador: 'neutral', certificado: 'success', aceptable: 'success',
  con_condiciones: 'warning', no_aceptable: 'danger', pass: 'success', attention: 'danger', info: 'info',
}

/** Pastilla de un estado del módulo con su texto `cert.estado_<valor>`. */
export function Estado({ valor }: { valor: string | null | undefined }) {
  const t = useAppT()
  if (!valor) return <span className="cert-apagado">—</span>
  return <StatusBadge kind={TONO[valor] ?? 'neutral'} caps={false}>{t(`cert.estado_${valor}`)}</StatusBadge>
}

/** Descarga un objeto como JSON (paquete del auditor, copia RGPD). */
export function descargarJson(nombre: string, datos: unknown) {
  const blob = new Blob([JSON.stringify(datos, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  a.click()
  URL.revokeObjectURL(url)
}

export interface PropsDePestana {
  /** Programa elegido en el selector de contexto (o vacío: todos). */
  programaId: string
}
