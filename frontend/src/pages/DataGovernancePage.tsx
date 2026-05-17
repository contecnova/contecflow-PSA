/**
 * DataGovernancePage — Gobernanza de datos.
 * GDPR/DSR, auditoría de accesos, linaje, clasificación de campos,
 * vistas compartidas, comentarios y bookmarks de dashboards.
 * Antes vivía en /bi tab "govern".
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Shield } from 'lucide-react'
import { COLOR } from '../constants/theme'
import { useAppLang } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import {
  biCollaborationApi,
  biBookmarksApi,
  biGovernanceAuditApi,
} from '../services/api'
import BiGdprPanel from '../components/bi/BiGdprPanel'
import BiGovernancePanel from '../components/bi/BiGovernancePanel'
import BiDashboardCollabPanel from '../components/bi/BiDashboardCollabPanel'

type ItemsResponse<T> = {
  items: T[]
}

type GovernanceOverview = {
  scheduled_reports?: number | { active?: number }
  anomalies_detected?: number
  checks_run?: number
}

type GovernanceRunResult = Record<string, unknown> | null

type AuditEvent = {
  user_id?: string
  resource?: string
  action?: string
  accessed_at?: string
}

type LineageEdge = {
  source_table?: string
  target_table?: string
  source?: string
  target?: string
}

type FieldSensitivity = {
  dataset_id?: string
  field_name?: string
  sensitivity?: string
}

type CommentItem = {
  id: string | number
  message?: string
  created_by_name?: string
  created_at?: string
  resolved?: boolean
}

type SharedView = {
  id: string | number
  name?: string
  dashboard_key?: string
  created_by_name?: string
  created_at?: string
  active?: boolean
}

type BookmarkItem = {
  id: string | number
  name?: string
  period_days?: number
  active_tab?: string
  description?: string
  shared?: boolean
}

type SharedViewsSort = 'date_desc' | 'date_asc' | 'author_asc' | 'name_asc'
type FieldSensitivityLevel = 'low' | 'medium' | 'high' | 'critical' | 'pii'

const S = {
  card:        { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' } as CSSProperties,
  cardPad:     { padding: '20px 24px' } as CSSProperties,
  input:       { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', borderRadius: 8, padding: '9px 13px', fontSize: 'var(--text-base)', fontFamily: 'inherit', outline: 'none', width: '100%' } as CSSProperties,
  btnPrimary:  { padding: '7px 16px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' } as CSSProperties,
  btnSecondary:{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' } as CSSProperties,
  btnAccentOutline: (c: string = COLOR.accent): CSSProperties => ({ padding: '7px 14px', borderRadius: 8, border: `1px solid ${c}`, background: `${c}18`, color: c, cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' }),
}

const getLocale = (lang: string) => (lang === 'en' ? 'en-US' : 'es-ES')
function toFiniteNumber(value: unknown, fallback = 0) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback
  if (typeof value === 'string') {
    const n = Number(value.trim())
    return Number.isFinite(n) ? n : fallback
  }
  return fallback
}

function SectionHeading({ title, description }: { title: string; description?: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h2 style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)', margin: '0 0 4px' }}>{title}</h2>
      {description && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', margin: 0 }}>{description}</p>}
    </div>
  )
}

export default function DataGovernancePage(): JSX.Element {
  const { lang } = useAppLang()
  const isMobile = useMediaQuery('(max-width: 900px)')

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
  const [newFieldSensitivity, setNewFieldSensitivity] = useState<FieldSensitivityLevel>('low')
  const [newFieldDataset, setNewFieldDataset] = useState('')

  // Collaboration queries
  const { data: commentsData, refetch: refetchComments } = useQuery<ItemsResponse<CommentItem>>({
    queryKey: ['data-gov-comments', commentWidget],
    queryFn: () => biCollaborationApi.listComments({ dashboard_key: 'executive', widget_id: commentWidget }).then(r => r.data as ItemsResponse<CommentItem>).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })
  const { data: sharedViewsData, refetch: refetchSharedViews } = useQuery<ItemsResponse<SharedView>>({
    queryKey: ['data-gov-shared-views', sharedViewsTick, showInactiveSharedViews],
    queryFn: () => biCollaborationApi.listSharedViews({ include_inactive: showInactiveSharedViews }).then(r => r.data as ItemsResponse<SharedView>).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })
  const { data: governance } = useQuery<GovernanceOverview | null>({
    queryKey: ['data-gov-overview'],
    queryFn: () => biCollaborationApi.governanceOverview().then(r => r.data as GovernanceOverview).catch(() => null),
    staleTime: 30_000,
  })
  const { refetch: refetchRules } = useQuery<unknown>({
    queryKey: ['data-gov-rules'],
    queryFn: () => biCollaborationApi.governanceRules().then(r => r.data).catch(() => null),
    staleTime: 30_000,
  })
  const { data: governanceRun, refetch: refetchGovRun } = useQuery<GovernanceRunResult>({
    queryKey: ['data-gov-run', govRunTick],
    queryFn: () => biCollaborationApi.lastGovernanceRun().then(r => (r.data?.result || null) as GovernanceRunResult).catch(() => null),
    staleTime: 10_000,
  })

  // Governance audit queries
  const { data: govAuditData } = useQuery<ItemsResponse<AuditEvent>>({
    queryKey: ['data-gov-audit', govAuditTick, govAuditUserFilter],
    queryFn: () => biGovernanceAuditApi.getAccessHistory(
      govAuditUserFilter.trim() ? { user_id: govAuditUserFilter.trim(), limit: 50 } : { limit: 50 }
    ).then(r => r.data as ItemsResponse<AuditEvent>).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })
  const { data: govLineageData, refetch: refetchGovLineage } = useQuery<ItemsResponse<LineageEdge>>({
    queryKey: ['data-gov-lineage', govAuditTick],
    queryFn: () => biGovernanceAuditApi.listLineage({}).then(r => r.data as ItemsResponse<LineageEdge>).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })
  const { data: govFieldData, refetch: refetchGovFields } = useQuery<ItemsResponse<FieldSensitivity>>({
    queryKey: ['data-gov-fields', govAuditTick],
    queryFn: () => biGovernanceAuditApi.listFieldSensitivity({}).then(r => r.data as ItemsResponse<FieldSensitivity>).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })
  const { data: bookmarks } = useQuery<ItemsResponse<BookmarkItem>>({
    queryKey: ['data-gov-bookmarks', bookmarksTick],
    queryFn: () => biBookmarksApi.list().then(r => r.data as ItemsResponse<BookmarkItem>).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })

  const comments = commentsData?.items || []
  const sharedViews = sharedViewsData?.items || []
  const sharedViewsQuery = sharedViewsSearch.trim().toLowerCase()
  const filteredSharedViews = sharedViews.filter(v => !sharedViewsQuery || String(v?.name || '').toLowerCase().includes(sharedViewsQuery))
  const sortedSharedViews = [...filteredSharedViews].sort((a, b) => {
    if (sharedViewsSort === 'name_asc') return String(a?.name || '').localeCompare(String(b?.name || ''), 'es', { sensitivity: 'base' })
    if (sharedViewsSort === 'author_asc') return String(a?.created_by_name || '').localeCompare(String(b?.created_by_name || ''), 'es', { sensitivity: 'base' })
    const tA = Date.parse(a?.created_at || '') || 0
    const tB = Date.parse(b?.created_at || '') || 0
    return sharedViewsSort === 'date_asc' ? tA - tB : tB - tA
  })
  const activeSharedViews = sharedViews.filter(v => v.active !== false).length
  const inactiveSharedViews = sharedViews.length - activeSharedViews
  const govScheduledActive = typeof governance?.scheduled_reports === 'object'
    ? toFiniteNumber(governance?.scheduled_reports?.active, 0)
    : toFiniteNumber(governance?.scheduled_reports, 0)

  // Handlers
  async function handleCreateComment() {
    const trimmed = (commentText || '').trim()
    if (!trimmed) return
    try {
      await biCollaborationApi.createComment({ dashboard_key: 'executive', widget_id: commentWidget, message: trimmed })
      setCommentText('')
      await refetchComments()
    } catch (_) { /* ignore */ }
  }
  async function handleResolveComment(id: string | number) {
    try { await biCollaborationApi.resolveComment(id); await refetchComments() } catch (_) { /* ignore */ }
  }
  async function handleCreateSharedView() {
    const name = (sharedViewName || '').trim()
    if (!name) return
    try {
      await biCollaborationApi.createSharedView({ name, dashboard_key: 'executive', filters: { days, widget_id: commentWidget } })
      setSharedViewName('')
      setSharedViewsTick(x => x + 1)
      await refetchSharedViews()
    } catch (_) { /* ignore */ }
  }
  async function handleToggleSharedView(view: SharedView) {
    try { await biCollaborationApi.patchSharedView(view.id, { active: !view.active }); setSharedViewsTick(x => x + 1); await refetchSharedViews() } catch (_) { /* ignore */ }
  }
  async function handleRunGovernance() {
    try { await biCollaborationApi.runGovernanceChecks(); setGovRunTick(x => x + 1); await refetchGovRun(); await refetchRules() } catch (_) { /* ignore */ }
  }
  async function handleLogGovAuditEvent() {
    try {
      await biGovernanceAuditApi.logAccessEvent({
        user_id: govAuditUserFilter.trim() || 'console',
        resource: 'bi_dashboard',
        action: 'view',
      })
      setGovAuditTick(x => x + 1)
    } catch (_) { /* ignore */ }
  }
  async function handleAddLineageEdge() {
    const src = newLineageSource.trim()
    const tgt = newLineageTarget.trim()
    if (!src || !tgt) return
    try {
      await biGovernanceAuditApi.trackLineage({ source_table: src, target_table: tgt })
      setNewLineageSource(''); setNewLineageTarget('')
      setGovAuditTick(x => x + 1)
    } catch (_) { /* ignore */ }
  }
  async function handleUpsertFieldSensitivity() {
    const field = newFieldName.trim()
    const dataset = newFieldDataset.trim()
    if (!field || !dataset) return
    try {
      await biGovernanceAuditApi.upsertFieldSensitivity({ dataset_id: dataset, field_name: field, sensitivity: newFieldSensitivity })
      setNewFieldName(''); setNewFieldDataset('')
      setGovAuditTick(x => x + 1)
    } catch (_) { /* ignore */ }
  }

  return (
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14 } : undefined}>
      <PageHeader
        icon={<Shield size={18} />}
        title="Data Governance"
        subtitle="GDPR, auditoría, linaje, clasificación de campos y colaboración en dashboards"
      showListExport={false}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

        <BiGdprPanel />
        <BiGovernancePanel />

        <div>
          <SectionHeading title="Auditoría y linaje" />
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 14 }}>

            {/* Audit trail */}
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Auditoría de accesos</span>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <input value={govAuditUserFilter} onChange={e => setGovAuditUserFilter(e.target.value)} placeholder="Filtrar por user_id"
                    style={{ ...S.input, width: 130, padding: '5px 10px', fontSize: 'var(--text-xs)' }} />
                  <button onClick={() => setGovAuditTick(x => x + 1)} style={{ ...S.btnSecondary, padding: '5px 10px', fontSize: 'var(--text-xs)' }}>Filtrar</button>
                </div>
              </div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                <button onClick={handleLogGovAuditEvent} style={S.btnAccentOutline()}>Registrar acceso</button>
                {(govAuditData?.items || []).length === 0
                  ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Sin eventos de auditoría</div>
                  : <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                      {(govAuditData?.items || []).slice(0, 20).map((ev, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                          <span style={{ fontSize: 'var(--text-2xs)', background: `${COLOR.info}18`, color: COLOR.info, borderRadius: 6, padding: '2px 7px', fontWeight: 700, flexShrink: 0 }}>{ev.action || 'view'}</span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-1)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.resource || '—'}</div>
                            <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{ev.user_id || '—'} · {ev.accessed_at ? new Date(ev.accessed_at).toLocaleString() : '—'}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                }
              </div>
            </div>

            {/* Lineage */}
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Linaje de datos</span>
                <button onClick={() => refetchGovLineage()} style={{ ...S.btnSecondary, padding: '5px 10px', fontSize: 'var(--text-xs)' }}>Refrescar</button>
              </div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input value={newLineageSource} onChange={e => setNewLineageSource(e.target.value)} placeholder="Tabla origen" style={{ ...S.input, flex: 1, minWidth: 80, padding: '6px 10px', fontSize: 'var(--text-xs)' }} />
                  <span style={{ color: 'var(--text-3)' }}>→</span>
                  <input value={newLineageTarget} onChange={e => setNewLineageTarget(e.target.value)} placeholder="Tabla destino" style={{ ...S.input, flex: 1, minWidth: 80, padding: '6px 10px', fontSize: 'var(--text-xs)' }} />
                  <button onClick={handleAddLineageEdge} style={{ ...S.btnAccentOutline(), padding: '6px 14px', fontSize: 'var(--text-xs)' }}>Añadir</button>
                </div>
                {(govLineageData?.items || []).length === 0
                  ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Sin edges de linaje</div>
                  : <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                      {(govLineageData?.items || []).slice(0, 20).map((edge, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{edge.source_table || edge.source || '—'}</span>
                          <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>→</span>
                          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-1)', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{edge.target_table || edge.target || '—'}</span>
                        </div>
                      ))}
                    </div>
                }
              </div>
            </div>

            {/* Field sensitivity */}
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Clasificación de campos</span>
                <button onClick={() => refetchGovFields()} style={{ ...S.btnSecondary, padding: '5px 10px', fontSize: 'var(--text-xs)' }}>Refrescar</button>
              </div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                  <input value={newFieldDataset} onChange={e => setNewFieldDataset(e.target.value)} placeholder="Dataset ID" style={{ ...S.input, padding: '6px 10px', fontSize: 'var(--text-xs)' }} />
                  <input value={newFieldName} onChange={e => setNewFieldName(e.target.value)} placeholder="Campo (ej. email)" style={{ ...S.input, padding: '6px 10px', fontSize: 'var(--text-xs)' }} />
                  <select value={newFieldSensitivity} onChange={e => setNewFieldSensitivity(e.target.value as FieldSensitivityLevel)} style={{ ...S.input, padding: '6px 10px', fontSize: 'var(--text-xs)' }}>
                    {(['low', 'medium', 'high', 'critical', 'pii'] as FieldSensitivityLevel[]).map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <button onClick={handleUpsertFieldSensitivity} style={{ ...S.btnAccentOutline(COLOR.warning), padding: '6px 14px', fontSize: 'var(--text-xs)' }}>Clasificar</button>
                </div>
                {(govFieldData?.items || []).length === 0
                  ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Sin campos clasificados</div>
                  : <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                      {(govFieldData?.items || []).slice(0, 20).map((f, i) => {
                        const sc = f.sensitivity === 'critical' || f.sensitivity === 'pii' ? COLOR.danger : f.sensitivity === 'high' ? COLOR.warning : COLOR.success
                        return (
                          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                            <span style={{ fontSize: 'var(--text-2xs)', background: `${sc}18`, color: sc, borderRadius: 6, padding: '2px 7px', fontWeight: 700, flexShrink: 0, textTransform: 'uppercase' }}>{f.sensitivity || '—'}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-1)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.field_name || '—'}</div>
                              <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{f.dataset_id || '—'}</div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                }
              </div>
            </div>
          </div>
        </div>

        <SectionHeading title="Compartir y colaborar" description="Vistas compartidas, comentarios por widget, bookmarks de equipo y collab en tiempo real" />

        <BiDashboardCollabPanel />

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>

          {/* Shared views */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Vistas compartidas</span>
            </div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <input value={sharedViewName} onChange={e => setSharedViewName(e.target.value)} placeholder="Nombre de la vista..."
                  style={{ ...S.input, flex: 1 }} />
                <button onClick={handleCreateSharedView} style={S.btnAccentOutline(COLOR.success)}>Guardar vista</button>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input value={sharedViewsSearch} onChange={e => setSharedViewsSearch(e.target.value)} placeholder="Buscar vista..."
                  style={{ ...S.input, flex: 1, minWidth: 160 }} />
                <select value={sharedViewsSort} onChange={e => setSharedViewsSort(e.target.value as SharedViewsSort)} style={{ ...S.input, width: 'auto' }}>
                  <option value="date_desc">Más recientes</option>
                  <option value="date_asc">Más antiguas</option>
                  <option value="author_asc">Autor (A-Z)</option>
                  <option value="name_asc">Nombre (A-Z)</option>
                </select>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-xs)', color: 'var(--text-2)', cursor: 'pointer' }}>
                <input type="checkbox" checked={showInactiveSharedViews} onChange={e => setShowInactiveSharedViews(e.target.checked)} />
                Mostrar inactivas ({activeSharedViews} activas{showInactiveSharedViews ? ` · ${inactiveSharedViews} inactivas` : ''})
              </label>
              <div style={{ display: 'grid', gap: 6, maxHeight: 260, overflowY: 'auto' }}>
                {sortedSharedViews.length === 0
                  ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
                      {sharedViews.length === 0 ? 'Sin vistas compartidas. Guarda una para empezar.' : 'Sin coincidencias.'}
                    </div>
                  : sortedSharedViews.map(v => (
                      <div key={v.id} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <div>
                          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>{v.name}</div>
                          <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{v.dashboard_key} · {v.created_by_name || '—'} · {v.active === false ? 'inactiva' : 'activa'}</div>
                        </div>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button onClick={() => handleToggleSharedView(v)}
                            style={{ ...S.btnAccentOutline(v.active ? COLOR.warning : COLOR.success), padding: '4px 8px', fontSize: 'var(--text-xs)' }}>
                            {v.active ? 'Desactivar' : 'Activar'}
                          </button>
                        </div>
                      </div>
                    ))
                }
              </div>
            </div>
          </div>

          {/* Comments */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Comentarios de widgets</span>
            </div>
            <div style={{ ...S.cardPad, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <select value={commentWidget} onChange={e => setCommentWidget(e.target.value)} style={S.input}>
                <option value="kpi_grid">KPI grid</option>
                <option value="health_chart">Estado de salud</option>
                <option value="profit_table">Rentabilidad por proyecto</option>
                <option value="ai_narrative">Narrativa IA</option>
              </select>
              <textarea value={commentText} onChange={e => setCommentText(e.target.value)} rows={3}
                placeholder="Añade un comentario para este widget..."
                style={{ ...S.input, resize: 'vertical' }} />
              <button onClick={handleCreateComment} style={S.btnAccentOutline()}>Guardar comentario</button>
              <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 10, display: 'grid', gap: 8, maxHeight: 200, overflowY: 'auto' }}>
                {comments.length === 0
                  ? <div style={{ color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>Sin comentarios para este widget</div>
                  : comments.map(c => (
                      <div key={c.id} style={{ padding: '8px 10px', background: 'var(--surface-3)', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{c.message}</div>
                          <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginTop: 2 }}>{c.created_by_name || '—'} · {c.created_at ? new Date(c.created_at).toLocaleString(getLocale(String(lang))) : ''}</div>
                        </div>
                        {!c.resolved && (
                          <button onClick={() => handleResolveComment(c.id)}
                            style={{ fontSize: 'var(--text-2xs)', color: COLOR.success, background: 'none', border: 'none', cursor: 'pointer', flexShrink: 0, fontFamily: 'inherit' }}>✓ Resolver</button>
                        )}
                      </div>
                    ))
                }
              </div>
            </div>
          </div>
        </div>

        {/* Bookmarks */}
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Bookmarks de dashboard</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input value={newBookmarkName} onChange={e => setNewBookmarkName(e.target.value)} placeholder="Nombre del bookmark"
                style={{ ...S.input, width: 200 }} />
              <button onClick={async () => {
                if (!newBookmarkName.trim()) return
                try {
                  await biBookmarksApi.create({ name: newBookmarkName, period_days: days, active_tab: 'executive', shared: false })
                  setNewBookmarkName('')
                  setBookmarksTick(x => x + 1)
                } catch (_) { /* ignore */ }
              }} style={S.btnPrimary}>Guardar vista actual</button>
            </div>
          </div>
          <div style={S.cardPad}>
            {!(bookmarks?.items || []).length
              ? <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)', padding: '16px 0' }}>Sin bookmarks guardados</div>
              : <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                  {(bookmarks?.items || []).map(bm => (
                    <div key={bm.id} style={{ ...S.card, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--text-1)' }}>🔖 {bm.name}</span>
                        <button onClick={async () => {
                          try { await biBookmarksApi.delete(bm.id); setBookmarksTick(x => x + 1) } catch (_) { /* ignore */ }
                        }}
                          style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }}>✕</button>
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Período: {bm.period_days}d · Tab: {bm.active_tab || 'executive'}</div>
                      {bm.description && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{bm.description}</div>}
                      {bm.shared && <span style={{ fontSize: 'var(--text-2xs)', padding: '3px 8px', borderRadius: 10, background: `${COLOR.success}18`, color: COLOR.success, fontWeight: 700, alignSelf: 'flex-start' }}>Compartido</span>}
                    </div>
                  ))}
                </div>
            }
          </div>
        </div>

        {/* Governance overview */}
        {governance && (
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Resumen de gobernanza</span>
              <button onClick={handleRunGovernance} style={S.btnAccentOutline()}>Ejecutar checks</button>
            </div>
            <div style={{ ...S.cardPad, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
              {[
                { label: 'Reports programados activos', value: govScheduledActive },
                { label: 'Anomalías detectadas',         value: governance?.anomalies_detected ?? 0 },
                { label: 'Checks ejecutados',            value: governance?.checks_run ?? 0 },
              ].map(k => (
                <div key={k.label} style={{ padding: '12px 16px', background: 'var(--surface-3)', borderRadius: 10 }}>
                  <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--text-1)', marginBottom: 4 }}>{k.value ?? '—'}</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{k.label}</div>
                </div>
              ))}
            </div>
            {governanceRun && (
              <div style={{ ...S.cardPad, borderTop: '1px solid var(--surface-4)', fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
                Último run: {JSON.stringify(governanceRun).slice(0, 200)}
              </div>
            )}
          </div>
        )}
      </div>
    </PageShell>
  )
}
