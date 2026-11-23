/**
 * PerformanceReviewsPage — Evaluaciones de rendimiento 360°
 *
 * Flujo completo:
 *   1) HR/Admin crea un ciclo (Q1 2025, Annual…) → status `draft`
 *      ↳ El ciclo nace con una plantilla de preguntas por defecto (5 ratings + 3 textos)
 *      ↳ HR/Admin puede personalizar la plantilla mientras el ciclo siga en borrador
 *   2) HR/Admin activa el ciclo                  → status `active`
 *   3) HR/Admin asigna evaluaciones (quién evalúa a quién)
 *      ↳ Al elegir un tipo (manager/par/upward) la UI restringe el evaluador
 *        al pool elegible según organigrama (manager_id) y equipo/departamento.
 *      ↳ Si un tipo no aplica para esa persona se deshabilita con explicación.
 *   4) Cada evaluador rellena su evaluación según las preguntas de la plantilla
 *   5) Evaluador envía → status `submitted`
 *   6) HR/Admin cierra el ciclo                  → status `closed` (read-only)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi } from '../services/api'
import { Button, Spinner, EmptyState, Page, Tabs } from '../components/ui'
import { Star, Plus, Clock, CheckCircle2, ListChecks, TrendingUp, Activity, Map as MapIcon } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import { type Cycle, NO_PERMISSION_TIP, type Review, TYPE_BY_ID } from './evaluaciones/compartido'
import { CycleCard, KPIDashboardTab, NewCycleModal } from './evaluaciones/Ciclos'
import { DevPlansTab } from './evaluaciones/PlanesDeDesarrollo'
import { AssignReviewModal, ReviewForm } from './evaluaciones/FormularioEvaluacion'
import { Campaign360Dashboard, History360Modal, New360CampaignModal } from './evaluaciones/Campanas360'
import './PerformanceReviewsPage.css'

// ── Page ───────────────────────────────────────────────────────────────────
export default function PerformanceReviewsPage() {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user, puede } = useAuth()
  const isManager = puede('evaluaciones.gestionar')

  const [tab, setTab] = useState('cycles')

  // Estado de modales agrupado. Cada propiedad es independiente y se asigna
  // mediante helpers locales para mantener una API similar a setState.
  const [modals, setModals] = useState<{
    showNewCycle: boolean
    editingReview: Review | null
    assigningCycle: Cycle | null
    campaigningCycle: Cycle | null
    openDashboardId: string | null
    historySubject: { id?: string; name?: string } | null
  }>({
    showNewCycle:     false,
    editingReview:    null,
    assigningCycle:   null,
    campaigningCycle: null,
    openDashboardId:  null,
    historySubject:   null,  // {id, name}
  })
  const setModal = (key: string, value: unknown) => setModals(m => ({ ...m, [key]: value }))
  const setShowNewCycle     = (v: boolean) => setModal('showNewCycle', v)
  const setEditingReview    = (v: Review | null) => setModal('editingReview', v)
  const setAssigningCycle   = (v: Cycle | null) => setModal('assigningCycle', v)
  const setCampaigningCycle = (v: Cycle | null) => setModal('campaigningCycle', v)
  const setOpenDashboardId  = (v: string | null) => setModal('openDashboardId', v)
  const setHistorySubject   = (v: { id?: string; name?: string } | null) => setModal('historySubject', v)
  const {
    showNewCycle, editingReview, assigningCycle,
    campaigningCycle, openDashboardId, historySubject,
  } = modals

  const { data: cycles = [], isLoading: loadingCycles } = useQuery<Cycle[]>({
    queryKey: ['perf-cycles'],
    queryFn: () => performanceApi.cycles().then(r => r.data),
  })
  const { data: myReviews = [], isLoading: loadingMine } = useQuery<Review[]>({
    queryKey: ['perf-my-reviews'],
    queryFn: () => performanceApi.myReviews().then(r => r.data),
  })

  const { mutate: activate } = useMutation({
    mutationFn: (id: string) => performanceApi.activateCycle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: closeCycle } = useMutation({
    mutationFn: (id: string) => performanceApi.closeCycle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // 16-11-2026: título = el del menú ("Evaluaciones de desempeño"); pestañas
  // con Tabs del kit (antes un control segmentado relleno propio); vacíos con
  // EmptyState e icono de 28 px como el resto; KPIs del panel con KpiCard.
  return (
    <Page
      icon={<Star size={18} />}
      title={t('nav.performance_reviews')}
      subtitle={t('performance.subtitle') || t('pagina_perf.ciclos_de_evaluacion_360_autoevaluacion_par')}
      rightActions={
        tab === 'cycles' && (
          <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
            <Button icon={<Plus size={14} />} onClick={() => setShowNewCycle(true)} disabled={!isManager}>
              {traducir('performancereviews.nuevo_ciclo')}
            </Button>
          </span>
        )
      }
    >
      <Tabs
        ariaLabel={t('nav.performance_reviews')}
        active={tab}
        onChange={setTab}
        items={[
          { id: 'cycles',  label: t('pagina_perf.ciclos'), icon: <ListChecks size={14} /> },
          { id: 'pending', label: t('pagina_perf.mis_evaluaciones'), icon: <Clock size={14} />, count: myReviews.length || undefined },
          { id: 'plans',   label: t('pagina_perf.mi_plan'), icon: <MapIcon size={14} /> },
          ...(isManager ? [{ id: 'kpis', label: t('pagina_perf.panel_hr'), icon: <Activity size={14} /> }] : []),
        ]}
      />

      {/* Panel KPIs (solo admin/HR) */}
      {tab === 'kpis' && isManager && <KPIDashboardTab cycles={cycles} />}

      {/* Plan de desarrollo (todos los usuarios ven el suyo) */}
      {tab === 'plans' && user && (
        <DevPlansTab subjectId={user.id} subjectName={user.full_name || t('pagina_perf.mi_plan')} />
      )}

      {/* Ciclos */}
      {tab === 'cycles' && (
        loadingCycles ? <Spinner /> : cycles.length === 0 ? (
          <EmptyState icon={<Star size={28} />}
            title={traducir('performancereviews.sin_ciclos_de_evaluacion')}
            description={isManager
              ? t('pagina_perf.crea_el_primer_ciclo_para_iniciar')
              : t('pagina_perf.cuando_rr_hh_inicie_un_ciclo')} />
        ) : (
          <div data-export-table="performance-cycles-list" className="ds-stack">
            {cycles.map(c => (
              <CycleCard key={c.id} cycle={c} isManager={isManager}
                onActivate={activate}
                onCloseCycle={closeCycle}
                onAssign={setAssigningCycle}
                onCreateCampaign={setCampaigningCycle}
                onOpenDashboard={setOpenDashboardId}
              />
            ))}
          </div>
        )
      )}

      {/* Mis evaluaciones pendientes */}
      {tab === 'pending' && (
        <>
          {/* Acceso a mi evolución 360° (siempre visible en la pestaña) */}
          <div className="ds-card--inset perf-row-17">
            <div>
              <div className="performance-reviews-page-e16">
                {traducir('performancereviews.mi_evolucion_360')}
              </div>
              <div className="ds-muted u-xs">
                {traducir('performancereviews.compara_tus_puntuaciones_others_vs_self_a')}
              </div>
            </div>
            <Button variant="secondary" size="sm"
              onClick={() => setHistorySubject({ id: user?.id, name: user?.full_name ?? undefined })}>
              <TrendingUp size={12} /> {traducir('performancereviews.ver_evolucion')}
            </Button>
          </div>

          {loadingMine ? <Spinner /> : myReviews.length === 0 ? (
            <EmptyState icon={<CheckCircle2 size={28} />}
              title={traducir('performancereviews.sin_evaluaciones_pendientes')}
              description={t('pagina_perf.cuando_alguien_te_asigne_una_evaluacion')} />
          ) : (
          <div data-export-table="performance-pending-list" className="ds-stack-sm">
            {myReviews.map(r => {
              const tipo = TYPE_BY_ID[r.review_type] || TYPE_BY_ID.peer
              const TypeIcon = tipo.Icon
              return (
                <div key={r.id} className="ds-card perf-box-36">
                  <div className="perf-row-18">
                    <TypeIcon size={16} />
                  </div>
                  <div className="u-flex1-min0">
                    <div className="perf-box-37">
                      {t('pagina_perf.evaluar_a')} {r.reviewee_name}
                    </div>
                    <div className="ds-muted">{t(tipo.label)} · {t(tipo.help)}</div>
                  </div>
                  <Button onClick={() => setEditingReview(r)}>{traducir('performancereviews.rellenar_evaluacion')}</Button>
                </div>
              )
            })}
          </div>
          )}
        </>
      )}

      {showNewCycle && <NewCycleModal existingCycles={cycles} onClose={() => setShowNewCycle(false)} />}
      {editingReview && <ReviewForm review={editingReview} onClose={() => setEditingReview(null)} />}
      {assigningCycle && <AssignReviewModal cycle={assigningCycle} onClose={() => setAssigningCycle(null)} />}
      {campaigningCycle && (
        <New360CampaignModal cycle={campaigningCycle}
          onClose={() => setCampaigningCycle(null)} />
      )}
      {openDashboardId && (
        <Campaign360Dashboard campaignId={openDashboardId}
          onClose={() => setOpenDashboardId(null)}
          onOpenHistory={(id, name) => setHistorySubject({ id, name })} />
      )}
      {historySubject && (
        <History360Modal subjectId={historySubject.id}
          subjectName={historySubject.name}
          onClose={() => setHistorySubject(null)} />
      )}
    </Page>
  )
}
