/**
 * Campañas 360: alta, panel, historial y listado.
 * Troceado de PerformanceReviewsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { type CSSProperties, useState, useEffect, useMemo, useId } from 'react'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi, usersApi } from '../../services/api'
import { Button, Checkbox, Modal, Pulsable, Select, Spinner, EmptyState, Input } from '../../components/ui'
import {
  Plus,
  User,
  Users as UsersIcon,
  Crown,
  ArrowUp,
  AlertCircle,
  Target,
  BarChart3,
  Lock,
  X,
  TrendingUp,
  History,
  FileDown,
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import {
  type Campaign,
  type CampaignDashboard,
  claveDeBloqueo,
  type Cycle,
  type EligiblePool,
  type EligibleUser,
  type History360,
  type HistoryPoint,
  type HistoryQuestion,
  isRatingKind,
  NO_PERMISSION_TIP,
  ratingMax,
  ScoreBar,
} from './compartido'

// ── New360CampaignModal: wizard que crea una campaña con todos sus evaluadores
export function New360CampaignModal({ cycle, onClose }: { cycle: Cycle; onClose: () => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  // Estado de la campaña agrupado en un único objeto. Se exponen setters
  // específicos para preservar la legibilidad de los handlers existentes.
  const [campaign, setCampaign] = useState<{
    subjectId: string; selfReview: boolean; managerId: string
    peerIds: string[]; upwardIds: string[]; threshold: number | string
  }>({
    subjectId: '',
    selfReview: true,
    managerId: '',
    peerIds: [],
    upwardIds: [],
    threshold: 3,
  })
  const { subjectId, selfReview, managerId, peerIds, upwardIds, threshold } = campaign
  const setSubjectId  = (v: string) => setCampaign(s => ({ ...s, subjectId: v }))
  const setSelfReview = (v: boolean) => setCampaign(s => ({ ...s, selfReview: v }))
  const setManagerId  = (v: string) => setCampaign(s => ({ ...s, managerId: v }))
  const setPeerIds    = (updater: string[] | ((prev: string[]) => string[])) => setCampaign(s => ({
    ...s, peerIds: typeof updater === 'function' ? updater(s.peerIds) : updater,
  }))
  const setUpwardIds  = (updater: string[] | ((prev: string[]) => string[])) => setCampaign(s => ({
    ...s, upwardIds: typeof updater === 'function' ? updater(s.upwardIds) : updater,
  }))
  const setThreshold  = (v: string) => setCampaign(s => ({ ...s, threshold: v }))

  const { data: users = [] } = useQuery({
    queryKey: ['users-for-360-campaign'],
    // `usersApi.list` ya devuelve el array (todasLasPaginas).
    queryFn: () => usersApi.list({ page_size: SELECTOR_LIST_SIZE }).then(r => r.data),
  })

  // Para cada tipo (excepto self) calculamos elegibilidad cuando hay subject
  const elQueries = useQueries({
    queries: ['manager', 'peer', 'upward'].map(t => ({
      queryKey: ['perf-eligible', cycle.id, subjectId, t],
      queryFn: (): Promise<EligiblePool> => performanceApi.eligibleReviewers(cycle.id, subjectId, t).then(r => r.data),
      enabled: !!subjectId,
    })),
  })
  const [managerData, peerData, upwardData] = elQueries.map(q => q.data)
  const managerOptions: EligibleUser[] = managerData?.users || []
  const peerOptions: EligibleUser[]    = peerData?.users    || []
  const upwardOptions: EligibleUser[]  = upwardData?.users  || []

  // Si hay un único manager elegible, lo preseleccionamos.
  // Omitimos managerId y setManagerId a propósito: managerId solo se usa para
  // evitar pisar una selección manual (la guard `!managerId` ya lo cubre);
  // incluirlo dispararía el efecto cuando el usuario eligiese, y setManagerId
  // es una función creada en cada render que provocaría re-ejecuciones inútiles.
  useEffect(() => {
    if (managerOptions.length === 1 && !managerId) setManagerId(managerOptions[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- omisión deliberada, ver arriba
  }, [managerOptions])

  // Cuando cambia el subject reseteamos selecciones derivadas
  useEffect(() => {
    setManagerId('')
    setPeerIds([])
    setUpwardIds([])
  }, [subjectId])

  const togglePeer   = (id: string) => setPeerIds  (s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])
  const toggleUpward = (id: string) => setUpwardIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  const totalReviewers = (selfReview ? 1 : 0) + (managerId ? 1 : 0) + peerIds.length + upwardIds.length

  const { mutate: create, isPending } = useMutation({
    mutationFn: () => performanceApi.createCampaign(cycle.id, {
      subject_id: subjectId,
      self_review: selfReview,
      manager_reviewer_id: managerId || null,
      peer_reviewer_ids: peerIds,
      upward_reviewer_ids: upwardIds,
      anonymity_threshold: Number(threshold) || 3,
      auto_activate: true,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-campaigns', cycle.id] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', cycle.id] })
      toast.success(t('pagina_perf.campana_360_creada_con_evaluador_es', { totalReviewers }))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_perf.error_al_crear_campana'))),
  })

  const canCreate = !!subjectId && totalReviewers > 0 && !isPending

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <Target size={16} /> {traducir('performancereviews.nueva_campana_360')}
      </span>}
      subtitle={t('pagina_perf.ciclo', { name: cycle.name })}
      width={680}>
      <div className="ds-stack perf-box-2">
        {/* Subject */}
        <div className="ds-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('pagina_perf.persona_evaluada')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={subjectId}
            onChange={e => setSubjectId(e.target.value)}>
            <option value="">{t('pagina_perf.selecciona')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
        </div>

        {!subjectId ? (
          <div className="ds-card--inset perf-box-5">
            <div className="ds-muted">{traducir('performancereviews.selecciona_primero_la_persona_a_evaluar_para')}</div>
          </div>
        ) : (
          <>
            {/* Self */}
            <div className="ds-card--inset perf-row-4">
              <Checkbox id="self-review-cb" className="perf-label-3" checked={!!selfReview} onChange={setSelfReview}
                label={<div className="perf-box-7">
                  <User size={12} className="perf-box-38" /> {traducir('performancereviews.autoevaluacion')}
                </div>}
                ayuda={traducir('performancereviews.la_propia_persona_se_evalua_recomendado_en')} />
            </div>

            {/* Manager */}
            <div className="ds-field">
              <label id={`${idCampo}-manager-et`} htmlFor={`${idCampo}-manager`} className="ds-field__label">
                <Crown size={11} className="perf-box-38" />{' '}{t('pagina_perf.manager')}
              </label>
              {managerData?.reason_blocked ? (
                <div className="performance-reviews-page-e11">
                  <AlertCircle size={12} /> {t(claveDeBloqueo('manager'))}
                </div>
              ) : (
                <Select suelto placeholder={false} id={`${idCampo}-manager`} value={managerId} onChange={e => setManagerId(e.target.value)}>
                  <option value="">{traducir('performancereviews.sin_manager')}</option>
                  {managerOptions.map(u => (
                    <option key={u.id} value={u.id}>{u.full_name}</option>
                  ))}
                </Select>
              )}
            </div>

            {/* Peers */}
            <div className="ds-field">
              <label className="ds-field__label">
                <UsersIcon size={11} className="perf-box-38" />{' '}{t('pagina_perf.pares')}
                <span className="ds-muted perf-label-4">
                  {t('pagina_perf.pares_seleccionados', { n: peerIds.length, total: peerOptions.length })}
                </span>
              </label>
              {peerData?.reason_blocked ? (
                <div className="performance-reviews-page-e11">
                  <AlertCircle size={12} /> {t(claveDeBloqueo('peer'))}
                </div>
              ) : peerOptions.length === 0 ? (
                <div className="ds-muted u-xs">
                  {traducir('performancereviews.sin_pares_elegibles')}
                </div>
              ) : (
                <div className="ds-row-wrap perf-box-8">
                  {peerOptions.map(u => {
                    const sel = peerIds.includes(u.id)
                    return (
                      <Pulsable key={u.id} onClick={() => togglePeer(u.id)}
                        className={`perf-btn-3 performa-sx4 ${sel ? 'performa-sx5' : 'performa-sx6'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        {u.full_name}
                        {u.team && <span className="perf-label-5">· {u.team}</span>}
                      </Pulsable>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Upward */}
            <div className="ds-field">
              <label className="ds-field__label">
                <ArrowUp size={11} className="perf-box-38" />{' '}{t('pagina_perf.reportes_directos_upward')}
                <span className="ds-muted perf-label-4">
                  ({upwardIds.length}/{upwardOptions.length})
                </span>
              </label>
              {upwardData?.reason_blocked ? (
                <div className="perf-row-5">
                  <AlertCircle size={12} /> {t(claveDeBloqueo('upward'))}
                </div>
              ) : upwardOptions.length === 0 ? (
                <div className="ds-muted u-xs">
                  {traducir('performancereviews.sin_reportes_directos')}
                </div>
              ) : (
                <div className="ds-row-wrap perf-box-8">
                  {upwardOptions.map(u => {
                    const sel = upwardIds.includes(u.id)
                    return (
                      <Pulsable key={u.id} onClick={() => toggleUpward(u.id)}
                        className={`perf-btn-3 performa-sx4 ${sel ? 'performa-sx5' : 'performa-sx6'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        {u.full_name}
                      </Pulsable>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Anonimización */}
            <div className="ds-field">
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">
                <Lock size={11} className="perf-box-38" /> {traducir('performancereviews.umbral_de_anonimizacion')}
              </label>
              <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" min={1} max={20} value={threshold} onChange={e => setThreshold(e.target.value)} inputClassName="perf-input-2" />
              <div className="ds-field__hint">
                {traducir('performancereviews.cuando_un_grupo_pares_upward_tenga_menos')}
              </div>
            </div>
          </>
        )}

        <div className="ds-row-between perf-box-9">
          <div className="ds-muted u-sm">
            {t('pagina_perf.total')}{' '}<strong className="u-text1">{totalReviewers}</strong>{' '}{t('pagina_perf.evaluador_es')}
          </div>
          <div className="perf-row-6">
            <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
            <Button onClick={() => create()} disabled={!canCreate} loading={isPending}>
              <Target size={13} /> {traducir('performancereviews.crear_campana_360')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ── Campaign360Dashboard: panel agregado y anonimizado por subject ─────────
export function Campaign360Dashboard({ campaignId, onClose, onOpenHistory }: {
  campaignId: string; onClose: () => void; onOpenHistory?: (id: string, name: string) => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const { data, isLoading } = useQuery<CampaignDashboard>({
    queryKey: ['perf-campaign-dashboard', campaignId],
    queryFn: () => performanceApi.campaignDashboard(campaignId).then(r => r.data),
  })

  const downloadPdf = async () => {
    try {
      const res = await performanceApi.campaignDashboardPdf(campaignId)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const name = data?.campaign?.subject_name?.replace(/\s+/g, '_') || 'subject'
      a.download = `360_${name}_${campaignId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(extractErr(e, t('pagina_perf.error_al_descargar_pdf')))
    }
  }

  if (isLoading || !data) {
    return (
      <Modal open onClose={onClose} title={t('pagina_perf.dashboard_360')} width={760}>
        <Spinner />
      </Modal>
    )
  }

  const c = data.campaign
  const groups = data.groups || {}
  const ratingQs = (data.questions || []).filter(q => isRatingKind(q.kind))
  const textQs   = (data.questions || []).filter(q => !isRatingKind(q.kind))

  const GROUP_META = [
    { id: 'self',    label: t('pagina_perf.self'),    Icon: User },
    { id: 'manager', label: t('pagina_perf.manager'), Icon: Crown },
    { id: 'peer',    label: t('pagina_perf.pares'),   Icon: UsersIcon },
    { id: 'upward',  label: t('pagina_perf.upward'),  Icon: ArrowUp },
  ]

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <BarChart3 size={16} />{' '}{t('pagina_perf.dashboard_360_2')}{' '}{c.subject_name}
      </span>}
      subtitle={t('pagina_perf.respuestas_umbral', { enviadas: data.total_submitted, total: data.total_assigned, umbral: data.anonymity_threshold })}
      width={760}>
      <div className="ds-stack perf-box-2">
        {/* Resumen por grupo */}
        <div className="ds-grid-cards perf-box-10">
          {GROUP_META.map(({ id, label, Icon }) => {
            const g = groups[id] || { count: 0, anonymized: false }
            return (
              <div key={id} className="ds-card--inset perf-box-5">
                <div className="perf-row-5">
                  <Icon size={11} /> {label}
                </div>
                <div className="perf-box-11">
                  {g.count}
                </div>
                {g.anonymized && (
                  <div className="perf-row-7">
                    <Lock size={9} />{' '}{t('pagina_perf.anonimizado')}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Comparación por pregunta tipo rating */}
        {ratingQs.length > 0 && (
          <div className="ds-card--inset perf-stack">
            <div className="ds-eyebrow">{traducir('performancereviews.comparacion_por_pregunta')}</div>
            {ratingQs.map(q => {
              const max = ratingMax(q)
              const cmp = data.comparison?.[q.key] || {}
              const selfVal = cmp.self
              const peersVal = cmp.peers
              const managerVal = cmp.manager
              const upwardVal = cmp.upward
              // Detectar gap self vs others (blind spot / hidden strength)
              const others = [peersVal, managerVal, upwardVal].filter(v => v != null)
              const othersAvg = others.length ? others.reduce((s, v) => s + v, 0) / others.length : null
              let gapBadge = null
              if (selfVal != null && othersAvg != null) {
                const diff = selfVal - othersAvg
                if (Math.abs(diff) >= 1) {
                  gapBadge = diff > 0
                    ? { text: t('pagina_perf.punto_ciego'), color: 'var(--warning)' }
                    : { text: t('pagina_perf.fortaleza_no_percibida'), color: 'var(--success)' }
                }
              }
              return (
                <div key={q.id}>
                  <div className="ds-row-between perf-box-12">
                    <div className="performance-reviews-page-e9">
                      {q.label}
                    </div>
                    {gapBadge && (
                      <span className="perf-label-6 performance-reviews-page-e2" style={{ '--performance-reviews-page-color': gapBadge.color } as CSSProperties}>
                        {gapBadge.text}
                      </span>
                    )}
                  </div>
                  <div className="perf-grid">
                    {GROUP_META.map(({ id, label }) => {
                      const key = id === 'peer' ? 'peers' : id
                      const v = cmp[key]
                      if (v == null) {
                        return (
                          <div key={id} className="ds-row perf-box-13">
                            <span className="perf-label-7">{label}</span>
                            <span className="ds-muted u-xs">—</span>
                          </div>
                        )
                      }
                      return (
                        <div key={id} className="ds-row perf-box-13">
                          <span className="perf-label-7">{label}</span>
                          <div className="u-flex1">
                            <ScoreBar value={v} max={max} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Comentarios de texto, agrupados y anonimizados si procede */}
        {textQs.length > 0 && (
          <div className="ds-stack-sm">
            <div className="ds-eyebrow">{t('pagina_perf.comentarios_cualitativos')}</div>
            {textQs.map(q => (
              <div key={q.id} className="ds-card--inset perf-box-14">
                <div className="perf-box-15">
                  {q.label}
                </div>
                {GROUP_META.map(({ id, label, Icon }) => {
                  const g = groups[id]
                  if (!g) return null
                  const items = g.text_by_question?.[q.key] || []
                  return (
                    <div key={id} className="perf-box-16">
                      <div className="ds-row perf-box-17">
                        <Icon size={11} /> {label}
                        {g.anonymized && (
                          <span className="perf-row-8">
                            <Lock size={9} />{' '}{t('pagina_perf.oculto_umbral', { n: g.count, umbral: data.anonymity_threshold })}
                          </span>
                        )}
                      </div>
                      {!g.anonymized && items.length === 0 && (
                        <div className="ds-muted perf-box-18">
                          {traducir('performancereviews.sin_respuestas')}
                        </div>
                      )}
                      {!g.anonymized && items.map((it, idx: number) => (
                        <div key={idx} className="perf-box-19">
                          {String(it.text)}
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        )}

        <div className="perf-row-9">
          <div className="perf-row-6">
            <Button variant="secondary"
              onClick={() => onOpenHistory?.(c.subject_id, c.subject_name)}>
              <TrendingUp size={13} /> {traducir('performancereviews.ver_evolucion_historica')}
            </Button>
            <Button variant="secondary" onClick={downloadPdf}>
              <FileDown size={13} />{' '}{t('pagina_perf.descargar_pdf')}
            </Button>
          </div>
          <Button variant="secondary" onClick={onClose}>
            <X size={13} />{' '}{t('pagina_perf.cerrar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── History360Modal: evolución del subject a lo largo de varios ciclos ────
export function History360Modal({ subjectId, subjectName, onClose }: {
  subjectId?: string; subjectName?: string; onClose: () => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data, isLoading } = useQuery<History360>({
    queryKey: ['perf-360-history', subjectId],
    queryFn: () => performanceApi.history360(subjectId).then(r => r.data),
  })

  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const series: HistoryPoint[] = useMemo(() => data?.series || [], [data?.series])
  // Recopilamos todas las question keys que aparecen al menos una vez
  const allQs = useMemo<HistoryQuestion[]>(() => {
    const map = new Map<string, HistoryQuestion>()
    for (const s of series) {
      for (const [k, v] of Object.entries(s.ratings || {})) {
        if (!map.has(k)) map.set(k, { key: k, label: v.label, max: v.scale_max })
      }
    }
    return [...map.values()]
  }, [series])

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <TrendingUp size={16} /> {traducir('performancereviews.evolucion_360')} {subjectName || data?.subject_name}
      </span>}
      subtitle={t('pagina_perf.campanas_con_respuestas', { length: series.length })}
      width={780}>
      {isLoading ? <Spinner /> : series.length === 0 ? (
        <EmptyState icon={<History size={28} />}
          title={traducir('performancereviews.sin_historico_aun')}
          description={t('pagina_perf.cuando_se_cierren_campanas_con_respuestas')} />
      ) : (
        <div className="ds-stack perf-box-3">
          {/* Cabecera con cycles */}
          <div className="perf-grid-2 performance-reviews-page-e5" style={{ '--performance-reviews-page-grid-template-columns': `220px repeat(${series.length}, 1fr)` } as CSSProperties}>
            <div className="ds-eyebrow perf-box-20">{t('pagina_perf.pregunta_2')}</div>
            {series.map(s => (
              <div key={s.campaign_id} className="perf-box-21">
                <div className="perf-box-22">
                  {s.cycle_name}
                </div>
                <div className="ds-muted perf-box-23">
                  {s.created_at}
                </div>
              </div>
            ))}
          </div>

          {/* Filas: una por pregunta de rating */}
          {allQs.map(q => (
            <div key={q.key} className="perf-grid-3 performance-reviews-page-e5" style={{ '--performance-reviews-page-grid-template-columns': `220px repeat(${series.length}, 1fr)` } as CSSProperties}>
              <div className="performance-reviews-page-e9">
                {q.label}
              </div>
              {series.map(s => {
                const r = s.ratings?.[q.key]
                if (!r) {
                  return <div key={s.campaign_id} className="ds-muted perf-box-24"
                   >—</div>
                }
                const others = r.others
                const self   = r.self
                return (
                  <div key={s.campaign_id} className="perf-stack-3">
                    {others != null && (
                      <div className="perf-row-10">
                        <span className="perf-label-8">{t('pagina_perf.otros')}</span>
                        <div className="u-flex1">
                          <ScoreBar value={others} max={q.max} />
                        </div>
                      </div>
                    )}
                    {self != null && (
                      <div className="perf-row-10">
                        <span className="perf-label-8">{t('pagina_perf.autoevaluacion')}</span>
                        <div className="u-flex1">
                          <ScoreBar value={self} max={q.max} />
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}
      <div className="perf-row-11">
        <Button variant="secondary" onClick={onClose}>
          <X size={13} />{' '}{t('pagina_perf.cerrar')}
        </Button>
      </div>
    </Modal>
  )
}

// ── CampaignsList: campañas 360° dentro de un ciclo ───────────────────────
export function CampaignsList({ cycle, isManager, onCreate, onOpenDashboard }: {
  cycle: Cycle; isManager: boolean; onCreate: (cycle: Cycle) => void; onOpenDashboard: (id: string) => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data: campaigns = [], isLoading } = useQuery<Campaign[]>({
    queryKey: ['perf-campaigns', cycle.id],
    queryFn: () => performanceApi.listCampaigns(cycle.id).then(r => r.data),
  })

  return (
    <div className="ds-card--inset perf-stack-2">
      <div className="ds-row-between">
        <div className="ds-eyebrow performance-reviews-page-e13">
          <Target size={12} /> {traducir('performancereviews.campanas_360')}{campaigns.length})
        </div>
        {cycle.status !== 'closed' && (
          <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
            <Button size="sm" onClick={() => onCreate(cycle)} disabled={!isManager}>
              <Plus size={11} /> {traducir('performancereviews.nueva_campana')}
            </Button>
          </span>
        )}
      </div>
      {isLoading ? <Spinner /> : campaigns.length === 0 ? (
        <div className="ds-muted u-sm">
          {traducir('performancereviews.sin_campanas_una_campana_agrupa_autoevaluacion_manager')}
        </div>
      ) : (
        <div className="ds-stack-sm">
          {campaigns.map(camp => {
            const total = camp.total_reviewers || 0
            const submitted = camp.submitted || 0
            const pct = total ? Math.round((submitted / total) * 100) : 0
            return (
              // Auditoría 2026-08 (P1-6): fila clicable sin vía de teclado.
              <div key={camp.id} className="ds-row-between performance-reviews-page-e6"
                role="button"
                tabIndex={0}
                aria-label={t('pagina_perf.abrir_campana_de', { subject_name: camp.subject_name })}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenDashboard(camp.id) }
                }}
                onClick={() => onOpenDashboard(camp.id)}>
                <div className="performance-reviews-page-e8">
                  <div className="performance-reviews-page-e16">
                    {camp.subject_name}
                  </div>
                  <div className="ds-muted u-xs">
                    {submitted}/{total}{' '}{t('pagina_perf.respuestas')}{pct}%) · {camp.status}
                    {' · '}
                    {Object.entries(camp.by_type || {})
                      .filter(([, n]) => n > 0)
                      .map(([t, n]) => `${t}:${n}`).join(' ')}
                  </div>
                </div>
                <div className="perf-row-12">
                  <BarChart3 size={13} />
                  <span className="perf-label-9">{t('pagina_perf.dashboard')}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
