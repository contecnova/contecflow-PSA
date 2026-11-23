/**
 * Tipos, constantes y utilidades compartidas de las evaluaciones de rendimiento.
 * Troceado de PerformanceReviewsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { CSSProperties } from 'react'
import type {
  Campana360,
  CicloDeEvaluacion,
  EvaluacionDeDesempeno,
  EvaluadoresElegibles,
  Historico360,
  KpisDeCiclo,
  KpisDeDesempeno,
  PanelDeCampana360,
  PlanDeDesarrollo,
  PreguntaDeEvaluacion,
  RespuestasDeEvaluacion,
} from '../../services/api/tipos-rendimiento'
import { User, Users as UsersIcon, Crown, ArrowUp } from 'lucide-react'

export const NO_PERMISSION_TIP = 'pagina_perf.solo_admin_rr_hh'

// ── Formas de la API: services/api/tipos-rendimiento.ts ────────────────────
export type Cycle = CicloDeEvaluacion

export type Review = EvaluacionDeDesempeno

export type Question = PreguntaDeEvaluacion

export type AnswerMap = RespuestasDeEvaluacion

/** Cuerpo de `ReviewQuestionIn` / `ReviewQuestionUpdate`. */
export type QuestionPayload = Partial<Pick<Question, 'key' | 'label' | 'hint' | 'kind' | 'required' | 'scale_min' | 'scale_max'>>

export type EligiblePool = EvaluadoresElegibles

export type EligibleUser = EvaluadoresElegibles['users'][number]

export type Campaign = Campana360

export type CampaignDashboard = PanelDeCampana360

export type History360 = Historico360

export type HistoryPoint = Historico360['series'][number]

export type OrgKpis = KpisDeDesempeno

export type CycleKpis = KpisDeCiclo

export type DevPlan = PlanDeDesarrollo

export interface HistoryQuestion {
  key: string
  label: string
  max: number
}

// ── Estilos compartidos ────────────────────────────────────────────────────
// Se extraen aquí los patrones inline más repetidos para reducir ruido en JSX
// y unificar el look. NO cambian el comportamiento visible.

// Genera estilo de chip toggle activo/inactivo (botones de selección de tipo,
// pares, upward, plantilla, etc.). El tamaño se pasa explícitamente para no
// alterar la apariencia.
// ── Catálogos ──────────────────────────────────────────────────────────────
export const STATUS_CFG = {
  draft:  { kind: 'neutral', label: 'pagina_perf.borrador' },
  active: { kind: 'accent',  label: 'pagina_perf.activo' },
  closed: { kind: 'success', label: 'pagina_perf.cerrado' },
}

/** Clave i18n del motivo por el que un tipo de evaluación no tiene evaluadores (23-11-2026). */
export const claveDeBloqueo = (tipo: string) => `pagina_perf.bloqueo_${tipo}`

export const REVIEW_TYPES = [
  { id: 'self',    Icon: User,      label: 'pagina_perf.autoevaluacion', help: 'pagina_perf.el_propio_empleado_se_evalua' },
  { id: 'peer',    Icon: UsersIcon, label: 'pagina_perf.par',            help: 'pagina_perf.companeros_del_mismo_equipo_o_departamento' },
  { id: 'manager', Icon: Crown,     label: 'pagina_perf.manager',        help: 'pagina_perf.el_responsable_directo_segun_organigrama' },
  { id: 'upward',  Icon: ArrowUp,   label: 'pagina_perf.upward',         help: 'pagina_perf.reportes_directos_evaluan_a_su_responsable' },
]

export const TYPE_BY_ID = Object.fromEntries(REVIEW_TYPES.map(t => [t.id, t]))

export const QUESTION_KINDS = [
  { id: 'rating_5',     label: 'pagina_perf.puntuacion_1_5' },
  { id: 'rating_10',    label: 'pagina_perf.puntuacion_1_10' },
  { id: 'scale_likert', label: 'pagina_perf.likert_1_5' },
  { id: 'yes_no',       label: 'pagina_perf.si_no' },
  { id: 'text_short',   label: 'pagina_perf.texto_corto' },
  { id: 'text_long',    label: 'pagina_perf.texto_largo' },
]

export const KIND_LABEL = Object.fromEntries(QUESTION_KINDS.map(k => [k.id, k.label]))

export const isRatingKind = (k: string) => k === 'rating_5' || k === 'rating_10' || k === 'scale_likert'

export const ratingMax = (q: Question) => q.scale_max ?? (q.kind === 'rating_10' ? 10 : 5)

export const ratingMin = (q: Question) => q.scale_min ?? 1

// ── ScoreBar ────────────────────────────────────────────────────────────────
export function ScoreBar({ value, max = 5 }: { value: number | null | undefined; max?: number }) {
  const pct = value ? (value / max) * 100 : 0
  const color = pct >= 80 ? 'var(--success)'
              : pct >= 60 ? 'var(--accent)'
              : pct >= 40 ? 'var(--warning)'
              : 'var(--danger)'
  return (
    <div className="u-row-center-8">
      <div className="perf-card">
        <div className="perf-box performance-reviews-page-e1" style={{ '--performance-reviews-page-width': `${pct}%`, '--performance-reviews-page-background': color } as CSSProperties} />
      </div>
      <span className="perf-label performance-reviews-page-e2" style={{ '--performance-reviews-page-color': color } as CSSProperties}>{value ? Number(value).toFixed(1) : '—'}</span>
    </div>
  )
}
