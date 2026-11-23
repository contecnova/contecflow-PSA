/**
 * Tipos, entidades, etiquetas y constantes compartidas de la bandeja y la administración de aprobaciones.
 * Troceado de ApprovalsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type ComponentProps, type CSSProperties, type ReactNode, lazy } from 'react'
import type { ResumenDePolitica } from '../../services/api/tipos-politicas'
import CondicionesDelFlujo from '../../components/aprobaciones/CondicionesDelFlujo'
import type { Tono } from '../../utils/umbrales'
import type {
  CargaDeAprobadores,
  CuelloDeBotella,
  CuellosDeBotella,
  EstadisticasDeAprobacion,
  FlujoDeAprobacion,
  GrupoDeAprobadores,
  PasoDeAprobacion,
  PlantillaDeFlujo,
  SimulacionDeFlujo,
  SolicitudPendienteDeMi,
} from '../../services/api/tipos-rendimiento'
import {
  Clock as ClockIcon,
  FileText,
  Receipt,
  RefreshCw,
  Flag,
  ShoppingCart,
  FileSignature,
  PiggyBank,
  ArrowLeftRight,
  LayoutGrid,
  Palmtree,
  Package,
  ClipboardList,
  Handshake,
  GitBranch,
  UserPlus,
  Tag,
  Plug,
  Laptop,
  Undo2,
  Circle,
  AlarmClockPlus,
  ShieldAlert,
} from 'lucide-react'

// Diseñador gráfico (tarea #26): carga @xyflow/react solo al abrirlo.
export const DisenadorDeFlujo = lazy(() => import('../../components/aprobaciones/DisenadorDeFlujo'))

export type T = (k: string, p?: Record<string, unknown> | string) => string

export type EntityConfig = { label: string; icon: ReactNode; color: string }

// 16-11-2026 (pasada de diseño): iconos lucide en vez de emojis.
export const ENTIDADES: Record<string, { icon: ReactNode; color: string }> = {
  document: { icon: <FileText size={14} />, color: 'var(--accent)' },
  timesheet: { icon: <ClockIcon size={14} />, color: 'var(--accent)' },
  expense: { icon: <Receipt size={14} />, color: 'var(--warning)' },
  change_request: { icon: <RefreshCw size={14} />, color: 'var(--purple)' },
  milestone: { icon: <Flag size={14} />, color: 'var(--success)' },
  purchase: { icon: <ShoppingCart size={14} />, color: 'var(--danger)' },
  invoice: { icon: <Receipt size={14} />, color: 'var(--warning)' },
  contract: { icon: <FileSignature size={14} />, color: 'var(--purple)' },
  budget: { icon: <PiggyBank size={14} />, color: 'var(--success)' },
  budget_transfer: { icon: <ArrowLeftRight size={14} />, color: 'var(--success)' },
  // Mejoras de mercado 16-11-2026: peticiones del catálogo del service desk.
  catalog_request: { icon: <LayoutGrid size={14} />, color: 'var(--accent)' },
  leave: { icon: <Palmtree size={14} />, color: 'var(--accent)' },
  deliverable: { icon: <Package size={14} />, color: 'var(--text-2)' },
  proposal: { icon: <ClipboardList size={14} />, color: 'var(--purple)' },
  subcontractor: { icon: <Handshake size={14} />, color: 'var(--warning)' },
  scope_change: { icon: <GitBranch size={14} />, color: 'var(--danger)' },
  hire: { icon: <UserPlus size={14} />, color: 'var(--success)' },
  price_change: { icon: <Tag size={14} />, color: 'var(--danger)' },
  // Revisión 2026-11: escritura de un agente externo con MCP_WRITE_MODE=approval
  mcp_action: { icon: <Plug size={14} />, color: 'var(--purple)' },
  // Licencias y hardware, fase 1: asignar una licencia o un equipo con aprobación.
  alm_assignment: { icon: <Laptop size={14} />, color: 'var(--accent)' },
  // Licencias fase 2: liberar una licencia sin uso (recuperación).
  license_reclaim: { icon: <Undo2 size={14} />, color: 'var(--warning)' },
  // 18-11-2026: peticiones de horas extra (/overtime).
  overtime: { icon: <AlarmClockPlus size={14} />, color: 'var(--warning)' },
  // 19-11-2026: excepción de una vulnerabilidad (CMDB de software).
  vuln_exception: { icon: <ShieldAlert size={14} />, color: 'var(--warning)' },
  // Migración 191: estado de cuenta / factura de un proveedor, por importe.
  supplier_statement: { icon: <Handshake size={14} />, color: 'var(--accent)' },
  // 22-11-2026: cargo interno (chargeback) que excede el presupuesto de la unidad.
  internal_charge: { icon: <Receipt size={14} />, color: 'var(--warning)' },
}

export const ICONO_ENTIDAD_DESCONOCIDA = <Circle size={14} />

/** Nombre de cada tipo de entidad: `approvals.entity_<tipo>`. */
export const entityLabels = (t: T): Record<string, EntityConfig> =>
  Object.fromEntries(Object.entries(ENTIDADES).map(([k, v]) => [k, { ...v, label: t(`approvals.entity_${k}`, k) }]))

export const approverTypeLabels = (t: T): Record<string, string> => ({
  user: t('approvals.approver_user'),
  role: t('approvals.approver_role'),
  manager: t('approvals.approver_manager'),
  any_in_department: t('approvals.approver_any_department'),
  group: t('approvals.grupo_de_aprobadores'),
})

export const CATEGORIAS_DE_DOCUMENTO = ['contract', 'deliverable', 'proposal', 'sop', 'requirements', 'meeting_notes', 'legal', 'other']

export const COLORES_DE_PASO = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--purple)', 'var(--danger)']

export const color = (c: string) => ({ '--apv-color': c } as CSSProperties)

/** Umbral → clase de nivel (alto/medio/bajo). */
/** 19-11-2026: clase del tono (umbrales UMBRAL_APROBACION_* de la empresa; antes 80/50 y 25/10 aquí). */
const NIVEL_DE_TONO: Record<Tono, string> = { danger: 'apv-nivel--alto', warning: 'apv-nivel--medio', success: 'apv-nivel--bajo' }

export const nivel = (tono: Tono | null | undefined) => NIVEL_DE_TONO[tono ?? 'success']

// Formas de las respuestas de /approvals: services/api/tipos-rendimiento.ts.
export type ApprovalStep = PasoDeAprobacion

export type ApprovalWorkflow = FlujoDeAprobacion

export type WorkflowTemplate = PlantillaDeFlujo

export type ApprovalGroup = GrupoDeAprobadores

/** Rev. 166: más el resumen de las políticas al abrirla y el origen del paso (si lo añadió una política). */
export type PendingRequest = SolicitudPendienteDeMi & { politica?: ResumenDePolitica | null; step_origin?: string | null }

export type ApprovalStats = EstadisticasDeAprobacion

export type SimulationResult = SimulacionDeFlujo

export type BottleneckItem = CuelloDeBotella

export type BottleneckSummary = CuellosDeBotella['summary']

export type WorkflowAtRisk = CuellosDeBotella['top_workflows'][number]

export type WeeklyRejection = CuellosDeBotella['trend'][number]

export type Recommendation = CuellosDeBotella['recommendations'][number]

export type BottlenecksResponse = CuellosDeBotella

export type ApproverLoadResponse = CargaDeAprobadores

export interface SimulationPayload {
  entity_type: string
  context: { category: string; department: string; amount?: number; requested_by_user_id?: string }
}

export type CondicionesDeDisparo = ComponentProps<typeof CondicionesDelFlujo>['actuales']

export interface GroupForm {
  name: string
  description: string
  member_ids: string[]
}
