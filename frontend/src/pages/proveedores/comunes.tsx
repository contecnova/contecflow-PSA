/**
 * Proveedores (19-11-2026): piezas compartidas por la lista, la ficha y Configuración.
 */
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, ShieldAlert, UserRound } from 'lucide-react'
import StatusBadge from '../../components/ui/StatusBadge'
import AvisoDeConfiguracion from '../../components/ui/AvisoDeConfiguracion'
import { proveedoresApi } from '../../services/api/proveedores'
import { projectsApi } from '../../services/api/projects'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import type { ReferenciasDeProveedores } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { TONO_CICLO, TONO_RIESGO, conRespaldo } from './logica'
import type { Traductor } from './logica'
import './Proveedores.css'

/** Proyectos activos para los selectores (contrato, paquete, consumo). */
export function useProyectosActivos() {
  const { data = [] } = useQuery({
    queryKey: ['projects', 'activos-proveedores'],
    queryFn: () => projectsApi.list().then(r => r.data.filter(p => p.status === 'active')),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
  return data
}

const SIN_REFERENCIAS: ReferenciasDeProveedores = {
  budgets: [], cost_centers: [], alm_contracts: [], service_items: [], uat_sessions: [], ci_types: [], ci_classes: [], software_products: [],
}

/**
 * Migración 191: datos reales para los selectores de la ficha (`GET /suppliers/references`):
 * presupuestos, centros de coste, contratos ALM, catálogo del service desk,
 * sesiones UAT del proyecto y, para la medición desde la CMDB, tipos, clases y productos de software.
 */
export function useReferencias({ projectId, subId }: { projectId?: string | null; subId?: string | null } = {}): ReferenciasDeProveedores {
  const { data } = useQuery({
    queryKey: ['suppliers', 'references', projectId || '', subId || ''],
    queryFn: () => proveedoresApi.referencias({ project_id: projectId, sub_id: subId }).then(r => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
    retry: false,
  })
  return data ?? SIN_REFERENCIAS
}

/**
 * Aviso de que a una acción le falta configuración (catálogo vacío, sin plantillas…).
 * Es el `AvisoDeConfiguracion` del kit (24-11-2026): explica qué falta y, solo a
 * quien puede abrir Configuración → Proveedores, enlaza allí; al resto, «Pídeselo a
 * tu administrador» (los módulos no llevan botón «Configurar»).
 */
export function FaltaConfigurar({ mensaje }: { mensaje: string }) {
  return <AvisoDeConfiguracion seccion="proveedores" tono="info">{mensaje}</AvisoDeConfiguracion>
}

/** Quién puede escribir y configurar (capacidades del backend). */
export function usePermisosDeProveedores() {
  const { puede } = useAuth()
  return { gestionar: puede('proveedores.gestionar'), configurar: puede('proveedores.config') }
}

/** Traductor de la pantalla con el tipo que usan los ayudantes. */
export function useT(): Traductor {
  return useAppT() as unknown as Traductor
}

/** Etiqueta de una clave de enumeración (`proveedores.<prefijo><clave>`), con la clave de respaldo. */
export const etiquetaDe = (t: Traductor, prefijo: string, clave: string | null | undefined) =>
  clave ? conRespaldo(t, `proveedores.${prefijo}${clave}`, clave) : '—'

/** Insignias de tipo, modos, ciclo de vida y riesgo de un proveedor. */
export function InsigniasDeProveedor({ sub, compacto = false }: { sub: Subcontratista; compacto?: boolean }) {
  const t = useT()
  const tipo = sub.kind || 'company'
  const ciclo = sub.lifecycle_status || (sub.is_active ? 'active' : 'offboarded')
  return (
    <div className="prv-insignias">
      <StatusBadge kind={tipo === 'freelance' ? 'purple' : 'accent'} caps={false}>
        {tipo === 'freelance' ? <UserRound size={11} aria-hidden /> : <Building2 size={11} aria-hidden />} {etiquetaDe(t, 'tipo_', tipo)}
      </StatusBadge>
      {!compacto && (sub.engagement_modes || []).map(m => (
        <StatusBadge key={m} kind="neutral" caps={false}>{etiquetaDe(t, 'modo_', m)}</StatusBadge>
      ))}
      <StatusBadge kind={TONO_CICLO[ciclo] || 'neutral'} caps={false}>{etiquetaDe(t, 'ciclo_', ciclo)}</StatusBadge>
      {sub.risk_level && (
        <StatusBadge kind={TONO_RIESGO[sub.risk_level] || 'neutral'} caps={false}>
          <ShieldAlert size={11} aria-hidden /> {t('proveedores.riesgo_n', { nivel: etiquetaDe(t, 'riesgo_', sub.risk_level) })}
        </StatusBadge>
      )}
    </div>
  )
}

/** Fila de definición etiqueta / valor de las fichas. */
export function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="prv-dato">
      <div className="prv-dato-etiqueta">{etiqueta}</div>
      <div className="prv-dato-valor">{children}</div>
    </div>
  )
}
