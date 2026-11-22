/**
 * DataGovernancePage — Gobernanza de datos.
 * GDPR/DSR, auditoría de accesos, linaje, clasificación de campos,
 * vistas compartidas, comentarios y bookmarks de dashboards.
 * Antes vivía en /bi tab "govern".
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDateTime, localeActivo } from '../utils/helpers'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { ArrowRight, Bookmark, Check, Eye, GitBranch, History, MessageSquare, Plus, RefreshCw, Search, Shield, ShieldCheck, Tags, X } from 'lucide-react'
import { Button, EmptyState, IconButton, KpiCard, SelectorDePeriodo, Select, Checkbox, Input, Textarea } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo } from '../utils/periodo'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useAppLang } from '../i18n/AppLangContext'
import {
  biCollaborationApi,
  biBookmarksApi,
  biGovernanceAuditApi,
} from '../services/api'
import type {
  AccesoBi, ComentarioBi, EjecucionDeGobiernoBi, LinajeBi, ListaConCuenta, MarcadorBi, NivelDeSensibilidadBi,
  ResumenDeGobiernoBi, ReglasDeGobiernoBi, SensibilidadDeCampoBi, VistaCompartidaBi,
} from '../services/api/tipos-grc'
import BiGdprPanel from '../components/bi/BiGdprPanel'
import BiGovernancePanel from '../components/bi/BiGovernancePanel'
import BiDashboardCollabPanel from '../components/bi/BiDashboardCollabPanel'
import { STALE_LIVE_MS, STALE_NEAR_LIVE_MS, STALE_SHORT_MS } from '../constants/timings'
import { AUDIT_LOG_PAGE_SIZE } from '../constants/pagination'
import './DataGovernancePage.css'

type SharedViewsSort = 'date_desc' | 'date_asc' | 'author_asc' | 'name_asc'

const NIVELES: readonly NivelDeSensibilidadBi[] = ['public', 'internal', 'confidential', 'restricted']

function SectionHeading({ id, title, description }: { id?: string; title: string; description?: string }) {
  return (
    <div className="dg-section-head">
      <h2 id={id} className="dg-section-title">{title}</h2>
      {description && <p className="dg-section-desc">{description}</p>}
    </div>
  )
}

export default function DataGovernancePage(): JSX.Element {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const locale = localeActivo(String(lang))

  // Defaults para shared views/bookmarks
  const [days] = useState(30)
  const [commentWidget, setCommentWidget] = useState('kpi_grid')
  const [commentText, setCommentText] = useState('')
  const [sharedViewName, setSharedViewName] = useState('')
  const [sharedViewsSearch, setSharedViewsSearch] = useState('')
  const [sharedViewsSort, setSharedViewsSort] = useState<SharedViewsSort>('date_desc')
  const [showInactiveSharedViews, setShowInactiveSharedViews] = useState(false)
  const [sharedViewsTick, setSharedViewsTick] = useState(0)
  const [govRunTick, setGovRunTick] = useState(0)

  const [bookmarksTick, setBookmarksTick] = useState(0)
  const [newBookmarkName, setNewBookmarkName] = useState('')

  const [govAuditTick, setGovAuditTick] = useState(0)
  const [govAuditUserFilter, setGovAuditUserFilter] = useState('')
  const [newLineageSource, setNewLineageSource] = useState('')
  const [newLineageTarget, setNewLineageTarget] = useState('')
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldSensitivity, setNewFieldSensitivity] = useState<NivelDeSensibilidadBi>('internal')
  const [newFieldDataset, setNewFieldDataset] = useState('')

  // Collaboration queries
  const { data: commentsData, refetch: refetchComments } = useQuery<ComentarioBi[]>({
    queryKey: ['data-gov-comments', commentWidget],
    queryFn: () => biCollaborationApi.listComments({ dashboard_key: 'executive', widget_id: commentWidget }).then(r => r.data).catch(() => []),
    staleTime: STALE_NEAR_LIVE_MS,
  })
  const { data: sharedViewsData, refetch: refetchSharedViews } = useQuery<VistaCompartidaBi[]>({
    queryKey: ['data-gov-shared-views', sharedViewsTick, showInactiveSharedViews],
    queryFn: () => biCollaborationApi.listSharedViews({ include_inactive: showInactiveSharedViews }).then(r => r.data).catch(() => []),
    staleTime: STALE_NEAR_LIVE_MS,
  })
  const { data: governance } = useQuery<ResumenDeGobiernoBi | null>({
    queryKey: ['data-gov-overview'],
    queryFn: () => biCollaborationApi.governanceOverview().then(r => r.data).catch(() => null),
    staleTime: STALE_SHORT_MS,
  })
  const { refetch: refetchRules } = useQuery<ReglasDeGobiernoBi | null>({
    queryKey: ['data-gov-rules'],
    queryFn: () => biCollaborationApi.governanceRules().then(r => r.data).catch(() => null),
    staleTime: STALE_SHORT_MS,
  })
  const { data: governanceRun, refetch: refetchGovRun } = useQuery<EjecucionDeGobiernoBi | null>({
    queryKey: ['data-gov-run', govRunTick],
    queryFn: () => biCollaborationApi.lastGovernanceRun().then(r => r.data?.result ?? null).catch(() => null),
    staleTime: STALE_LIVE_MS,
  })

  // Governance audit queries
  // Periodo libre (16-11-2026): antes 30 días fijos (el defecto de la API).
  const periodoAuditoria = usePeriodo({ defecto: '30d', granularidades: CON_HORA, prefijo: 'dgaud' })
  const { data: govAuditData, error: govAuditError } = useQuery<ListaConCuenta<AccesoBi>>({
    queryKey: ['data-gov-audit', govAuditTick, govAuditUserFilter, periodoAuditoria.params],
    queryFn: () => biGovernanceAuditApi.getAccessHistory(
      govAuditUserFilter.trim()
        ? { ...periodoAuditoria.params, user_id: govAuditUserFilter.trim(), limit: AUDIT_LOG_PAGE_SIZE }
        : { ...periodoAuditoria.params, limit: AUDIT_LOG_PAGE_SIZE }
    ).then(r => r.data).catch((e: unknown) => {
      if (codigoDeErrorDePeriodo(e)) throw e
      return { items: [], count: 0 }
    }),
    staleTime: STALE_NEAR_LIVE_MS,
  })
  const { data: govLineageData, refetch: refetchGovLineage } = useQuery<ListaConCuenta<LinajeBi>>({
    queryKey: ['data-gov-lineage', govAuditTick],
    queryFn: () => biGovernanceAuditApi.listLineage().then(r => r.data).catch(() => ({ items: [], count: 0 })),
    staleTime: STALE_NEAR_LIVE_MS,
  })
  const { data: govFieldData, refetch: refetchGovFields } = useQuery<ListaConCuenta<SensibilidadDeCampoBi>>({
    queryKey: ['data-gov-fields', govAuditTick],
    queryFn: () => biGovernanceAuditApi.listFieldSensitivity().then(r => r.data).catch(() => ({ items: [], count: 0 })),
    staleTime: STALE_NEAR_LIVE_MS,
  })
  const { data: bookmarks } = useQuery<ListaConCuenta<MarcadorBi>>({
    queryKey: ['data-gov-bookmarks', bookmarksTick],
    queryFn: () => biBookmarksApi.list().then(r => r.data).catch(() => ({ items: [], count: 0 })),
    staleTime: STALE_SHORT_MS,
  })

  // Comentarios y vistas son APIListResponse (llegan como lista); auditoría, linaje,
  // campos y marcadores responden `{items, count}` dentro de `data`.
  const comments = commentsData ?? []
  const sharedViews = sharedViewsData ?? []
  const govAuditItems = govAuditData?.items ?? []
  const govAuditErrorDePeriodo = codigoDeErrorDePeriodo(govAuditError)
  const govLineageItems = govLineageData?.items ?? []
  const govFieldItems = govFieldData?.items ?? []
  const bookmarkItems = bookmarks?.items ?? []
  const sharedViewsQuery = sharedViewsSearch.trim().toLowerCase()
  const filteredSharedViews = sharedViews.filter(v => !sharedViewsQuery || String(v?.name || '').toLowerCase().includes(sharedViewsQuery))
  const sortedSharedViews = [...filteredSharedViews].sort((a, b) => {
    if (sharedViewsSort === 'name_asc') return String(a?.name || '').localeCompare(String(b?.name || ''), locale, { sensitivity: 'base' })
    if (sharedViewsSort === 'author_asc') return String(a?.created_by_name || '').localeCompare(String(b?.created_by_name || ''), locale, { sensitivity: 'base' })
    const tA = Date.parse(a?.created_at || '') || 0
    const tB = Date.parse(b?.created_at || '') || 0
    return sharedViewsSort === 'date_asc' ? tA - tB : tB - tA
  })
  const activeSharedViews = sharedViews.filter(v => v.active !== false).length
  const inactiveSharedViews = sharedViews.length - activeSharedViews
  const govScheduledActive = governance?.scheduled_reports?.active ?? 0

  // Handlers
  async function handleCreateComment() {
    const trimmed = (commentText || '').trim()
    if (!trimmed) return
    try {
      await biCollaborationApi.createComment({ dashboard_key: 'executive', widget_id: commentWidget, message: trimmed })
      setCommentText('')
      await refetchComments()
    } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }
  async function handleResolveComment(id: string | number) {
    try { await biCollaborationApi.resolveComment(id); await refetchComments() } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }
  async function handleCreateSharedView() {
    const name = (sharedViewName || '').trim()
    if (!name) return
    try {
      await biCollaborationApi.createSharedView({ name, dashboard_key: 'executive', filters: { days, widget_id: commentWidget } })
      setSharedViewName('')
      setSharedViewsTick(x => x + 1)
      await refetchSharedViews()
    } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }
  async function handleToggleSharedView(view: VistaCompartidaBi) {
    try { await biCollaborationApi.patchSharedView(view.id, { active: !view.active }); setSharedViewsTick(x => x + 1); await refetchSharedViews() } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }
  async function handleRunGovernance() {
    try { await biCollaborationApi.runGovernanceChecks(); setGovRunTick(x => x + 1); await refetchGovRun(); await refetchRules() } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }
  async function handleAddLineageEdge() {
    const src = newLineageSource.trim()
    const tgt = newLineageTarget.trim()
    if (!src || !tgt) return
    try {
      await biGovernanceAuditApi.trackLineage({ source_table: src, target_table: tgt })
      setNewLineageSource(''); setNewLineageTarget('')
      setGovAuditTick(x => x + 1)
    } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }
  async function handleUpsertFieldSensitivity() {
    const field = newFieldName.trim()
    const dataset = newFieldDataset.trim()
    if (!field || !dataset) return
    try {
      await biGovernanceAuditApi.upsertFieldSensitivity({ dataset_id: dataset, field_name: field, sensitivity_level: newFieldSensitivity })
      setNewFieldName(''); setNewFieldDataset('')
      setGovAuditTick(x => x + 1)
    } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
  }

  return (
    <PageShell className="dg-page">
      <PageHeader
        icon={<Shield size={18} />}
        title={t('nav.data_governance')}
        subtitle={t('datagovernance.subtitulo')}
        showListExport={false}
      />

      <div className="u-stack-20">

        <BiGdprPanel />
        <BiGovernancePanel />

        <section aria-labelledby="dg-auditoria">
          <SectionHeading id="dg-auditoria" title={t('datagovernance.auditoria_y_linaje')} />
          <div className="dg-grid3">

            {/* Audit trail */}
            <div className="dg-card">
              <div className="dg-card__head">
                <h3 className="dg-card__title">{t('datagovernance.auditoria_de_accesos')}</h3>
                <div className="u-row-center-6">
                  <input aria-label={t('datagovernance.filtrar_por_user_id')} value={govAuditUserFilter} onChange={e => setGovAuditUserFilter(e.target.value)} placeholder={t('datagovernance.filtrar_por_user_id')}
                    className="dg-input dg-input--filter" />
                  <Button size="sm" variant="secondary" icon={<Search size={14} />} onClick={() => setGovAuditTick(x => x + 1)}>{t('datagovernance.filtrar')}</Button>
                </div>
              </div>
              <div className="dg-card__body">
                <SelectorDePeriodo {...periodoAuditoria.selector} sinGranularidad />
                {govAuditErrorDePeriodo
                  ? <EmptyState icon={<History size={28} />} title={t(`periodo_err.${govAuditErrorDePeriodo.motivo}`, govAuditErrorDePeriodo.params)} />
                  : govAuditItems.length === 0
                  ? <EmptyState icon={<History size={28} />} title={t('datagovernance.sin_eventos_de_auditoria')} />
                  : <div className="dg-list">
                      {govAuditItems.slice(0, 20).map((ev, i) => (
                        <div key={i} className="dg-item">
                          <span className="dg-tag dg-c-accent">{etiquetaCodigo(t, 'datagovernance.accion', ev.action || 'view')}</span>
                          <div className="u-flex1-min0">
                            <div className="dg-item__title">{ev.entity_id || ev.entity_type || '—'}</div>
                            <div className="u-text3-2xs">{ev.user_name || ev.user_id || '—'} · {fmtDateTime(ev.timestamp)}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                }
              </div>
            </div>

            {/* Lineage */}
            <div className="dg-card">
              <div className="dg-card__head">
                <h3 className="dg-card__title">{t('datagovernance.linaje_de_datos')}</h3>
                <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetchGovLineage()}>{t('datagovernance.refrescar')}</Button>
              </div>
              <div className="dg-card__body">
                <div className="dg-form-row">
                  <input aria-label={t('datagovernance.tabla_origen')} value={newLineageSource} onChange={e => setNewLineageSource(e.target.value)} placeholder={t('datagovernance.tabla_origen')} className="dg-input dg-input--xs dg-input--grow" />
                  <ArrowRight size={14} className="u-text3" aria-hidden="true" />
                  <input aria-label={t('datagovernance.tabla_destino')} value={newLineageTarget} onChange={e => setNewLineageTarget(e.target.value)} placeholder={t('datagovernance.tabla_destino')} className="dg-input dg-input--xs dg-input--grow" />
                  <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={handleAddLineageEdge}>{t('datagovernance.anadir')}</Button>
                </div>
                {govLineageItems.length === 0
                  ? <EmptyState icon={<GitBranch size={28} />} title={t('datagovernance.sin_edges_de_linaje')} />
                  : <div className="dg-list">
                      {govLineageItems.slice(0, 20).map((edge, i) => (
                        <div key={i} className="dg-item dg-item--gap6">
                          <span className="dg-lineage-cell">{edge.source_table || '—'}</span>
                          <ArrowRight size={13} className="u-text3" aria-label={t('datagovernance.hacia')} />
                          <span className="dg-lineage-cell dg-lineage-cell--target">{edge.target_table || '—'}</span>
                        </div>
                      ))}
                    </div>
                }
              </div>
            </div>

            {/* Field sensitivity */}
            <div className="dg-card">
              <div className="dg-card__head">
                <h3 className="dg-card__title">{t('datagovernance.clasificacion_de_campos')}</h3>
                <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetchGovFields()}>{t('datagovernance.refrescar')}</Button>
              </div>
              <div className="dg-card__body">
                <div className="dg-form-grid">
                  <Input aria-label={t('datagovernance.dataset_id')} value={newFieldDataset} onChange={e => setNewFieldDataset(e.target.value)} placeholder={t('datagovernance.dataset_id')} inputClassName="dg-input dg-input--xs" />
                  <Input aria-label={t('datagovernance.campo_ejemplo')} value={newFieldName} onChange={e => setNewFieldName(e.target.value)} placeholder={t('datagovernance.campo_ejemplo')} inputClassName="dg-input dg-input--xs" />
                  <Select suelto placeholder={false} aria-label={t('datagovernance.nivel_de_sensibilidad')} value={newFieldSensitivity} onChange={e => setNewFieldSensitivity(e.target.value as NivelDeSensibilidadBi)} className="dg-input dg-input--xs">
                    {NIVELES.map((s) => <option key={s} value={s}>{t(`datagovernance.sens_${s}`)}</option>)}
                  </Select>
                  <Button size="sm" variant="secondary" icon={<Tags size={14} />} onClick={handleUpsertFieldSensitivity}>{t('datagovernance.clasificar')}</Button>
                </div>
                {govFieldItems.length === 0
                  ? <EmptyState icon={<Tags size={28} />} title={t('datagovernance.sin_campos_clasificados')} />
                  : <div className="dg-list">
                      {govFieldItems.slice(0, 20).map((f, i) => {
                        const sc = f.sensitivity_level === 'restricted' ? 'danger' : f.sensitivity_level === 'confidential' ? 'warning' : 'success'
                        return (
                          <div key={i} className="dg-item">
                            <span className={`dg-tag dg-tag--upper dg-c-${sc}`}>{f.sensitivity_level && (NIVELES as readonly string[]).includes(f.sensitivity_level) ? t(`datagovernance.sens_${f.sensitivity_level}`) : (f.sensitivity_level || '—')}</span>
                            <div className="u-flex1-min0">
                              <div className="dg-item__title">{f.field_name || '—'}</div>
                              <div className="u-text3-2xs">{f.dataset_id || '—'}</div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                }
              </div>
            </div>
          </div>
        </section>

        <SectionHeading title={t('datagovernance.compartir_y_colaborar')} description={t('datagovernance.compartir_y_colaborar_desc')} />

        <BiDashboardCollabPanel />

        <div className="dg-grid2">

          {/* Shared views */}
          <div className="dg-card">
            <div className="dg-card__head">
              <h3 className="dg-card__title">{t('datagovernance.vistas_compartidas')}</h3>
            </div>
            <div className="dg-card__body dg-card__body--gap10">
              <div className="u-row-8">
                <input aria-label={t('datagovernance.nombre_de_la_vista')} value={sharedViewName} onChange={e => setSharedViewName(e.target.value)} placeholder={t('datagovernance.nombre_de_la_vista')}
                  className="dg-input dg-input--fill" />
                <Button size="sm" icon={<Plus size={14} />} onClick={handleCreateSharedView}>{t('datagovernance.guardar_vista')}</Button>
              </div>
              <div className="u-wrap-center-8">
                <input aria-label={t('datagovernance.buscar_vista')} value={sharedViewsSearch} onChange={e => setSharedViewsSearch(e.target.value)} placeholder={t('datagovernance.buscar_vista')}
                  className="dg-input dg-input--search" />
                <Select suelto placeholder={false} aria-label={t('datagovernance.ordenar_vistas')} value={sharedViewsSort} onChange={e => setSharedViewsSort(e.target.value as SharedViewsSort)} className="dg-input dg-input--auto">
                  <option value="date_desc">{t('datagovernance.mas_recientes')}</option>
                  <option value="date_asc">{t('datagovernance.mas_antiguas')}</option>
                  <option value="author_asc">{t('datagovernance.autor_az')}</option>
                  <option value="name_asc">{t('datagovernance.nombre_az')}</option>
                </Select>
              </div>
              <label className="dg-check">
                <Checkbox aria-label={t('datagovernance.mostrar_inactivas')} checked={showInactiveSharedViews} onChange={(_, e) => setShowInactiveSharedViews(e.target.checked)} />
                {showInactiveSharedViews
                  ? t('datagovernance.mostrar_inactivas_con_ambas', { activas: activeSharedViews, inactivas: inactiveSharedViews })
                  : t('datagovernance.mostrar_inactivas_con_activas', { activas: activeSharedViews })}
              </label>
              <div className="dg-views">
                {sortedSharedViews.length === 0
                  ? <EmptyState icon={<Eye size={28} />} title={sharedViews.length === 0 ? t('datagovernance.sin_vistas_compartidas') : t('datagovernance.sin_coincidencias')} />
                  : sortedSharedViews.map(v => (
                      <div key={v.id} className="dg-view">
                        <div className="u-min0">
                          <div className="u-text1-sm-600">{v.name}</div>
                          <div className="u-text3-2xs">{etiquetaCodigo(t, 'datagovernance.panel', v.dashboard_key)} · {v.created_by_name || '—'} · {v.active === false ? t('datagovernance.inactiva') : t('datagovernance.activa')}</div>
                        </div>
                        <div className="u-row-6">
                          <Button size="sm" variant="secondary" onClick={() => handleToggleSharedView(v)}>
                            {v.active ? t('datagovernance.desactivar') : t('datagovernance.activar')}
                          </Button>
                        </div>
                      </div>
                    ))
                }
              </div>
            </div>
          </div>

          {/* Comments */}
          <div className="dg-card">
            <div className="dg-card__head">
              <h3 className="dg-card__title">{t('datagovernance.comentarios_de_widgets')}</h3>
            </div>
            <div className="dg-card__body dg-card__body--gap10">
              <Select suelto placeholder={false} aria-label={t('datagovernance.widget')} value={commentWidget} onChange={e => setCommentWidget(e.target.value)} className="dg-input">
                <option value="kpi_grid">{t('datagovernance.widget_kpi_grid')}</option>
                <option value="health_chart">{t('datagovernance.estado_de_salud')}</option>
                <option value="profit_table">{t('datagovernance.rentabilidad_por_proyecto')}</option>
                <option value="ai_narrative">{t('datagovernance.widget_narrativa_ia')}</option>
              </Select>
              <Textarea aria-label={t('datagovernance.anade_un_comentario_para_este_widget')} value={commentText} onChange={e => setCommentText(e.target.value)} rows={3} placeholder={t('datagovernance.anade_un_comentario_para_este_widget')} inputClassName="dg-input" />
              <div><Button size="sm" icon={<MessageSquare size={14} />} onClick={handleCreateComment}>{t('datagovernance.guardar_comentario')}</Button></div>
              <div className="dg-comments">
                {comments.length === 0
                  ? <EmptyState icon={<MessageSquare size={28} />} title={t('datagovernance.sin_comentarios_para_este_widget')} />
                  : comments.map(c => (
                      <div key={c.id} className="dg-comment">
                        <div className="u-flex1-min0">
                          <div className="dg-comment__msg">{c.message}</div>
                          <div className="dg-comment__meta">{c.author_name || '—'} · {c.created_at ? fmtDateTime(c.created_at) : ''}</div>
                        </div>
                        {!c.resolved && (
                          <Button size="sm" variant="ghost" icon={<Check size={14} />} onClick={() => handleResolveComment(c.id)}>
                            {t('datagovernance.resolver')}
                          </Button>
                        )}
                      </div>
                    ))
                }
              </div>
            </div>
          </div>
        </div>

        {/* Bookmarks */}
        <div className="dg-card">
          <div className="dg-card__head dg-card__head--gap8">
            <h3 className="dg-card__title">{t('datagovernance.bookmarks_de_dashboard')}</h3>
            <div className="u-row-center-8">
              <input aria-label={t('datagovernance.nombre_del_bookmark')} value={newBookmarkName} onChange={e => setNewBookmarkName(e.target.value)} placeholder={t('datagovernance.nombre_del_bookmark')}
                className="dg-input dg-input--bookmark" />
              <Button size="sm" icon={<Bookmark size={14} />} onClick={async () => {
                if (!newBookmarkName.trim()) return
                try {
                  await biBookmarksApi.create({ name: newBookmarkName, period_days: days, active_tab: 'executive', shared: false })
                  setNewBookmarkName('')
                  setBookmarksTick(x => x + 1)
                } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
              }}>{t('datagovernance.guardar_vista_actual')}</Button>
            </div>
          </div>
          <div className="dg-card__body dg-card__body--block">
            {!bookmarkItems.length
              ? <EmptyState icon={<Bookmark size={28} />} title={t('datagovernance.sin_bookmarks_guardados')} />
              : <div className="dg-bm-grid">
                  {bookmarkItems.map(bm => (
                    <div key={bm.id} className="dg-card dg-bm">
                      <div className="u-row-between">
                        <span className="dg-bm__name"><Bookmark size={13} aria-hidden="true" />{bm.name}</span>
                        <IconButton ariaLabel={t('datagovernance.eliminar_bookmark', { name: bm.name })} onClick={async () => {
                          try { await biBookmarksApi.delete(bm.id); setBookmarksTick(x => x + 1) } catch (e) { toast.error(extractErr(e, t('datagovernance.error_guardar'))) }
                        }}
                          className="dg-del"><X size={14} /></IconButton>
                      </div>
                      <div className="u-text3-xs">{t('datagovernance.periodo')} {t('datagovernance.n_dias', { n: bm.period_days })} · {t('datagovernance.pestana')} {etiquetaCodigo(t, 'datagovernance.panel', bm.active_tab || 'executive')}</div>
                      {bm.description && <div className="u-text2-xs">{bm.description}</div>}
                      {bm.shared && <span className="dg-badge dg-c-success">{t('datagovernance.compartido')}</span>}
                    </div>
                  ))}
                </div>
            }
          </div>
        </div>

        {/* Governance overview */}
        {governance && (
          <div className="dg-card">
            <div className="dg-card__head">
              <h3 className="dg-card__title">{t('datagovernance.resumen_de_gobernanza')}</h3>
              <Button size="sm" variant="secondary" icon={<ShieldCheck size={14} />} onClick={handleRunGovernance}>{t('datagovernance.ejecutar_checks')}</Button>
            </div>
            <div className="ds-grid-stats dg-kpis">
              <KpiCard label={t('datagovernance.kpi_reports_programados')} value={govScheduledActive} />
              {/* Revisión 2026-11: estas dos cifras leían campos que no existen y daban 0 siempre. */}
              <KpiCard label={t('datagovernance.kpi_hallazgos')} value={governanceRun ? (governanceRun.finding_count ?? 0) : '—'}
                warning={(governanceRun?.finding_count ?? 0) > 0} />
              <KpiCard label={t('datagovernance.kpi_ultima_comprobacion')} value={governanceRun?.timestamp ? fmtDateTime(governanceRun.timestamp) : '—'} />
            </div>
            {governanceRun && (
              <div className="dg-findings">
                {(governanceRun.findings ?? []).length === 0
                  ? t('datagovernance.sin_hallazgos')
                  : (governanceRun.findings ?? []).map((f, i) => (
                    <div key={i} className={f.severity === 'critical' ? 'dg-finding dg-finding--critical' : 'dg-finding'}>• {f.message}</div>
                  ))}
              </div>
            )}
          </div>
        )}
      </div>
    </PageShell>
  )
}
